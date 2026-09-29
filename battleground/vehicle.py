"""战场载具与攻城系统。

规则：
1. 载具数量受团队人数与资源双重限制；
2. 上/下车有冷却，且高级载具需要驾驶资格；
3. 攻城武器需要架设时间，架设中可被打断；
4. 血量按载具类型与等级区分；
5. 维修有冷却且消耗材料，每次只能修复部分血量；
6. 载具击杀/助攻计入驾驶员个人贡献与积分；
7. 载具消耗燃油，耗尽后必须补给或弃车。
"""
from dataclasses import dataclass, field

ENTER_COOLDOWN = 3.0
REPAIR_COOLDOWN = 4.0
REPAIR_PER_ACTION = 25.0
MATERIAL_PER_HP = 1.0
HP_BONUS_PER_LEVEL = 0.1
KILL_SCORE = 100.0
ASSIST_SCORE = 30.0
KILL_CONTRIBUTION = 10.0
ASSIST_CONTRIBUTION = 3.0


@dataclass(frozen=True)
class VehicleSpec:
    name: str
    base_hp: float
    fuel_capacity: float
    fuel_burn: float
    cost: int
    license_level: int
    deploy_duration: float


VEHICLE_SPECS: dict[str, VehicleSpec] = {
    "scout": VehicleSpec("侦察车", 100.0, 80.0, 1.0, 50, 1, 0.0),
    "tank": VehicleSpec("主战坦克", 250.0, 150.0, 3.0, 200, 2, 0.0),
    "siege": VehicleSpec("攻城车", 400.0, 200.0, 4.0, 300, 3, 5.0),
}


@dataclass
class Vehicle:
    vid: str
    type: str
    level: int = 1
    hp: float = 100.0
    max_hp: float = 100.0
    fuel: float = 100.0
    max_fuel: float = 100.0
    team: str | None = None
    owner: str | None = None
    driver: str | None = None
    deploy_time: float = 0.0
    deploying: bool = False
    interrupted: bool = False
    destroyed: bool = False


class VehicleError(RuntimeError):
    pass


class VehicleSystem:
    def __init__(self):
        self.vehicles: dict[str, Vehicle] = {}
        self.team_vehicles: dict[str, list[str]] = {}
        self.enter_cd: dict[str, float] = {}
        self.repair_cd: dict[str, float] = {}
        self.player_licenses: dict[str, int] = {}
        self.vehicle_kills: dict[str, int] = {}
        self.vehicle_assists: dict[str, int] = {}
        self.player_kills: dict[str, int] = {}
        self.player_assists: dict[str, int] = {}
        self.player_scores: dict[str, float] = {}
        self.player_contribution: dict[str, float] = {}
        self.resources_spent: dict[str, int] = {}
        self.repair_materials_spent: dict[str, float] = {}

    def _spec(self, vtype: str) -> VehicleSpec:
        spec = VEHICLE_SPECS.get(vtype)
        if spec is None:
            raise VehicleError(f"未知载具类型: {vtype}")
        return spec

    def get_vehicle_limit(self, team_size: int) -> int:
        if team_size <= 0:
            return 0
        return max(1, min(8, team_size // 3 + 1))

    def team_vehicle_count(self, team: str) -> int:
        return sum(
            1
            for vid in self.team_vehicles.get(team, [])
            if not self.vehicles[vid].destroyed
        )

    def get_vehicle_hp(self, vtype: str, level: int = 1) -> float:
        spec = self._spec(vtype)
        return spec.base_hp * (1.0 + HP_BONUS_PER_LEVEL * max(0, level - 1))

    def set_license(self, player: str, level: int) -> None:
        self.player_licenses[player] = max(1, level)

    def get_license(self, player: str) -> int:
        return self.player_licenses.get(player, 1)

    def spawn_vehicle(
        self,
        vid: str,
        vtype: str,
        team: str,
        team_size: int,
        resources: int,
        current_time: float = 0.0,
        level: int = 1,
        owner: str | None = None,
    ) -> Vehicle:
        if vid in self.vehicles:
            raise VehicleError(f"载具已存在: {vid}")
        spec = self._spec(vtype)
        if self.team_vehicle_count(team) >= self.get_vehicle_limit(team_size):
            raise VehicleError("团队载具数量已达上限")
        if resources < spec.cost:
            raise VehicleError("资源不足，无法生产载具")
        hp = self.get_vehicle_hp(vtype, level)
        needs_deploy = spec.deploy_duration > 0
        vehicle = Vehicle(
            vid=vid,
            type=vtype,
            level=max(1, level),
            hp=hp,
            max_hp=hp,
            fuel=spec.fuel_capacity,
            max_fuel=spec.fuel_capacity,
            team=team,
            owner=owner,
            deploy_time=float("inf") if needs_deploy else 0.0,
            deploying=needs_deploy,
        )
        self.vehicles[vid] = vehicle
        self.team_vehicles.setdefault(team, []).append(vid)
        self.resources_spent[team] = self.resources_spent.get(team, 0) + spec.cost
        return vehicle

    def can_enter_vehicle(
        self, player: str, current_time: float, vid: str | None = None
    ) -> bool:
        if self.enter_cd.get(player, 0.0) > current_time:
            return False
        if vid is None:
            return True
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed or vehicle.driver is not None:
            return False
        return self.get_license(player) >= self._spec(vehicle.type).license_level

    def enter_vehicle(self, player: str, vid: str, current_time: float) -> bool:
        if not self.can_enter_vehicle(player, current_time, vid):
            return False
        vehicle = self.vehicles[vid]
        vehicle.driver = player
        self.enter_cd[player] = current_time + ENTER_COOLDOWN
        return True

    def exit_vehicle(self, player: str, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.driver != player:
            return False
        vehicle.driver = None
        self.enter_cd[player] = current_time + ENTER_COOLDOWN
        return True

    def start_deploy(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed:
            return False
        spec = self._spec(vehicle.type)
        if spec.deploy_duration <= 0:
            vehicle.deploy_time = 0.0
            vehicle.deploying = False
            return True
        vehicle.deploying = True
        vehicle.interrupted = False
        vehicle.deploy_time = current_time + spec.deploy_duration
        return True

    def interrupt_deploy(self, vid: str) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.deploying:
            return False
        vehicle.deploying = False
        vehicle.interrupted = True
        vehicle.deploy_time = float("inf")
        return True

    def is_deployed(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed or vehicle.interrupted:
            return False
        if current_time >= vehicle.deploy_time:
            vehicle.deploying = False
            return True
        return False

    def can_fire(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        return (
            vehicle is not None
            and not vehicle.destroyed
            and self.is_deployed(vid, current_time)
        )

    def can_repair(self, vid: str, current_time: float) -> bool:
        if self.repair_cd.get(vid, 0.0) > current_time:
            return False
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed or vehicle.hp >= vehicle.max_hp:
            return False
        return True

    def repair_vehicle(self, vid: str, current_time: float, materials: float) -> float:
        if not self.can_repair(vid, current_time):
            return 0.0
        vehicle = self.vehicles[vid]
        healed = min(
            REPAIR_PER_ACTION,
            vehicle.max_hp - vehicle.hp,
            max(0.0, materials) / MATERIAL_PER_HP,
        )
        if healed <= 0:
            return 0.0
        vehicle.hp += healed
        self.repair_materials_spent[vid] = (
            self.repair_materials_spent.get(vid, 0.0) + healed * MATERIAL_PER_HP
        )
        self.repair_cd[vid] = current_time + REPAIR_COOLDOWN
        return healed

    def record_vehicle_kill(
        self,
        vid: str,
        current_time: float = 0.0,
        assists: tuple[str, ...] = (),
    ) -> str | None:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed:
            return None
        self.vehicle_kills[vid] = self.vehicle_kills.get(vid, 0) + 1
        killer = vehicle.driver or vehicle.owner
        if killer is not None:
            self.player_kills[killer] = self.player_kills.get(killer, 0) + 1
            self.player_scores[killer] = (
                self.player_scores.get(killer, 0.0) + KILL_SCORE
            )
            self.player_contribution[killer] = (
                self.player_contribution.get(killer, 0.0) + KILL_CONTRIBUTION
            )
        for assistant in assists:
            self.vehicle_assists[vid] = self.vehicle_assists.get(vid, 0) + 1
            self.player_assists[assistant] = self.player_assists.get(assistant, 0) + 1
            self.player_scores[assistant] = (
                self.player_scores.get(assistant, 0.0) + ASSIST_SCORE
            )
            self.player_contribution[assistant] = (
                self.player_contribution.get(assistant, 0.0) + ASSIST_CONTRIBUTION
            )
        return killer

    def get_kill_contribution(self, vid: str) -> float:
        kills = self.vehicle_kills.get(vid, 0)
        assists = self.vehicle_assists.get(vid, 0)
        return kills * KILL_CONTRIBUTION + assists * ASSIST_CONTRIBUTION

    def get_player_score(self, player: str) -> float:
        return self.player_scores.get(player, 0.0)

    def get_player_contribution(self, player: str) -> float:
        return self.player_contribution.get(player, 0.0)

    def get_fuel_consumption(self, vtype: str) -> float:
        return self._spec(vtype).fuel_burn

    def can_move(self, vid: str) -> bool:
        vehicle = self.vehicles.get(vid)
        return vehicle is not None and not vehicle.destroyed and vehicle.fuel > 0.0

    def move_vehicle(self, vid: str, duration: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed or vehicle.fuel <= 0.0 or duration <= 0:
            return False
        burn = self._spec(vehicle.type).fuel_burn * duration
        vehicle.fuel = max(0.0, vehicle.fuel - burn)
        return vehicle.fuel > 0.0

    def refuel_vehicle(self, vid: str, amount: float) -> float:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or amount <= 0:
            return 0.0
        before = vehicle.fuel
        vehicle.fuel = min(vehicle.max_fuel, vehicle.fuel + amount)
        return vehicle.fuel - before

    def abandon_vehicle(self, player: str, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.driver != player:
            return False
        vehicle.driver = None
        self.enter_cd[player] = current_time + ENTER_COOLDOWN
        return True

    def apply_damage(self, vid: str, amount: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.destroyed:
            return False
        vehicle.hp = max(0.0, vehicle.hp - max(0.0, amount))
        if vehicle.hp <= 0.0:
            vehicle.destroyed = True
            vehicle.driver = None
        return vehicle.destroyed
