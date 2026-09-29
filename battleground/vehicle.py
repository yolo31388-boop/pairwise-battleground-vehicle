"""战场载具与攻城系统

修复7个PVP问题:
1. 载具数量按团队人数与资源限制
2. 上下车冷却 + 驾驶资格
3. 攻城武器架设时间, 架设中可被打断
4. 血量按类型/等级区分
5. 维修冷却 + 材料消耗, 每次只修一部分
6. 载具击杀/助攻计入个人贡献与积分
7. 燃油限制, 耗尽需补给或弃车
"""
from dataclasses import dataclass

# 类型基础属性: 血量/燃油消耗(每秒)/造价/架设时间
VEHICLE_STATS = {
    "scout": {"hp": 100.0, "fuel_rate": 1.0, "cost": 50.0, "deploy": 0.0},
    "tank":  {"hp": 300.0, "fuel_rate": 2.5, "cost": 120.0, "deploy": 0.0},
    "siege": {"hp": 400.0, "fuel_rate": 0.8, "cost": 200.0, "deploy": 5.0},
}

ENTER_COOLDOWN = 3.0      # 上/下车冷却(秒)
REPAIR_COOLDOWN = 10.0    # 维修冷却(秒)
REPAIR_RATIO = 0.25       # 单次维修恢复最大血量比例
REPAIR_MATERIAL_COST = 20.0
KILL_POINTS = 100
ASSIST_POINTS = 30
KILL_CONTRIBUTION = 10.0
ASSIST_CONTRIBUTION = 3.0
MEMBERS_PER_VEHICLE = 3   # 每3名队员允许1辆载具(+1保底)


class VehicleError(Exception):
    """载具操作非法时抛出"""


@dataclass
class Vehicle:
    vid: str
    type: str  # tank/scout/siege
    hp: float = 100
    max_hp: float = 100
    fuel: float = 100
    deploy_time: float = 0
    level: int = 1
    team: str = ""
    driver: str | None = None
    alive: bool = True
    abandoned: bool = False


class VehicleSystem:
    def __init__(self):
        self.vehicles: dict[str, Vehicle] = {}
        self.team_vehicles: dict[str, list] = {}
        # 上/下车共用操作冷却, 防止瞬间反复切换载具
        self.enter_cd: dict[str, float] = {}
        self.repair_cd: dict[str, float] = {}
        # bug6修复: 载具击杀/助攻记录
        self.vehicle_kills: dict[str, int] = {}
        self.vehicle_assists: dict[str, int] = {}
        # 个人积分与贡献
        self.player_scores: dict[str, float] = {}
        self.player_contrib: dict[str, dict] = {}
        # 团队资源(含维修材料)
        self.team_resources: dict[str, float] = {}
        # 驾驶资格: player -> 允许驾驶的类型集合
        self.licenses: dict[str, set] = {}
        # 攻城架设状态: vid -> {"start": float, "interrupted": bool}
        self.deploy_state: dict[str, dict] = {}

    # ---- bug1: 数量/资源限制 ----
    def get_vehicle_limit(self, team_size: int) -> int:
        """每3名队员允许1辆载具, 至少1辆"""
        if team_size <= 0:
            return 0
        return 1 + team_size // MEMBERS_PER_VEHICLE

    def team_vehicle_count(self, team: str) -> int:
        return len([
            vid for vid in self.team_vehicles.get(team, [])
            if self.vehicles.get(vid) and self.vehicles[vid].alive
        ])

    def add_team_resources(self, team: str, amount: float) -> None:
        self.team_resources[team] = self.team_resources.get(team, 0.0) + amount

    def can_spawn_vehicle(self, team: str, vtype: str, team_size: int) -> bool:
        if vtype not in VEHICLE_STATS:
            return False
        if self.team_vehicle_count(team) >= self.get_vehicle_limit(team_size):
            return False
        return self.team_resources.get(team, 0.0) >= VEHICLE_STATS[vtype]["cost"]

    def spawn_vehicle(self, vid: str, team: str, vtype: str,
                      team_size: int, current_time: float, level: int = 1) -> Vehicle:
        if vid in self.vehicles:
            raise VehicleError(f"载具 {vid} 已存在")
        if not self.can_spawn_vehicle(team, vtype, team_size):
            raise VehicleError("载具数量或团队资源不足, 无法生产")
        self.team_resources[team] -= VEHICLE_STATS[vtype]["cost"]
        hp = self.get_vehicle_hp(vtype, level)
        vehicle = Vehicle(
            vid=vid, type=vtype, hp=hp, max_hp=hp, fuel=100.0,
            deploy_time=VEHICLE_STATS[vtype]["deploy"],
            level=level, team=team,
        )
        self.vehicles[vid] = vehicle
        self.team_vehicles.setdefault(team, []).append(vid)
        if vehicle.deploy_time > 0:
            self.deploy_state[vid] = {"start": current_time, "interrupted": False}
        return vehicle

    # ---- bug2: 上下车冷却 + 驾驶资格 ----
    def grant_license(self, player: str, vtype: str) -> None:
        self.licenses.setdefault(player, set()).add(vtype)

    def revoke_license(self, player: str, vtype: str) -> None:
        self.licenses.get(player, set()).discard(vtype)

    def is_licensed(self, player: str, vtype: str) -> bool:
        return vtype in self.licenses.get(player, set())

    def can_enter_vehicle(self, player: str, current_time: float,
                          vtype: str | None = None) -> bool:
        if current_time < self.enter_cd.get(player, 0.0):
            return False
        if vtype is not None and not self.is_licensed(player, vtype):
            return False
        return True

    def enter_vehicle(self, player: str, vid: str, current_time: float) -> None:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive:
            raise VehicleError("载具不存在或已损毁")
        if vehicle.driver is not None:
            raise VehicleError("载具已有人驾驶")
        if vehicle.abandoned and vehicle.fuel <= 0:
            raise VehicleError("载具燃油耗尽, 需先补给")
        if not self.can_enter_vehicle(player, current_time, vehicle.type):
            if not self.is_licensed(player, vehicle.type):
                raise VehicleError("无该载具驾驶资格")
            raise VehicleError("上下车冷却中")
        vehicle.driver = player
        self.enter_cd[player] = current_time + ENTER_COOLDOWN

    def exit_vehicle(self, player: str, vid: str, current_time: float) -> None:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or vehicle.driver != player:
            raise VehicleError("玩家不在驾驶该载具")
        if current_time < self.enter_cd.get(player, 0.0):
            raise VehicleError("上下车冷却中")
        vehicle.driver = None
        self.enter_cd[player] = current_time + ENTER_COOLDOWN

    # ---- bug3: 攻城架设时间, 可打断 ----
    def _needs_deploy(self, vehicle: Vehicle) -> bool:
        return vehicle.type == "siege" and vehicle.deploy_time > 0

    def is_deployed(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive:
            return False
        if not self._needs_deploy(vehicle):
            return True
        state = self.deploy_state.get(vid)
        if state is None:
            # 直接构造的载具: 视为从时刻0开始架设
            return current_time >= vehicle.deploy_time
        if state["interrupted"]:
            return False
        return current_time >= state["start"] + vehicle.deploy_time

    def is_deploying(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not self._needs_deploy(vehicle):
            return False
        state = self.deploy_state.get(vid)
        if state is None:
            return 0.0 <= current_time < vehicle.deploy_time
        if state["interrupted"]:
            return False
        return state["start"] <= current_time < state["start"] + vehicle.deploy_time

    def interrupt_deploy(self, vid: str) -> None:
        """架设中受到攻击/干扰, 架设被打断"""
        if vid in self.deploy_state:
            self.deploy_state[vid]["interrupted"] = True

    def start_deploy(self, vid: str, current_time: float) -> None:
        """被打断后重新架设"""
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not self._needs_deploy(vehicle):
            raise VehicleError("该载具不需要架设")
        self.deploy_state[vid] = {"start": current_time, "interrupted": False}

    def can_fire(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive or vehicle.driver is None:
            return False
        return self.is_deployed(vid, current_time)

    # ---- bug4: 血量按类型/等级 ----
    def get_vehicle_hp(self, vtype: str, level: int = 1) -> float:
        stats = VEHICLE_STATS.get(vtype)
        if stats is None:
            raise VehicleError(f"未知载具类型: {vtype}")
        return stats["hp"] * (1.0 + 0.25 * (max(level, 1) - 1))

    def damage(self, vid: str, amount: float, current_time: float = 0.0) -> None:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive:
            return
        vehicle.hp = max(0.0, vehicle.hp - amount)
        if self.is_deploying(vid, current_time):
            self.interrupt_deploy(vid)
        if vehicle.hp <= 0:
            vehicle.alive = False
            vehicle.driver = None

    # ---- bug5: 维修冷却 + 材料, 不能瞬间修满 ----
    def can_repair(self, vid: str, current_time: float) -> bool:
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive or vehicle.hp >= vehicle.max_hp:
            return False
        return current_time >= self.repair_cd.get(vid, 0.0)

    def repair_vehicle(self, vid: str, current_time: float) -> float:
        vehicle = self.vehicles.get(vid)
        if vehicle is None:
            raise VehicleError("载具不存在")
        if not self.can_repair(vid, current_time):
            raise VehicleError("维修冷却中或无需维修")
        resources = self.team_resources.get(vehicle.team, 0.0)
        if resources < REPAIR_MATERIAL_COST:
            raise VehicleError("维修材料不足")
        self.team_resources[vehicle.team] -= REPAIR_MATERIAL_COST
        before = vehicle.hp
        vehicle.hp = min(vehicle.max_hp,
                         vehicle.hp + vehicle.max_hp * REPAIR_RATIO)
        self.repair_cd[vid] = current_time + REPAIR_COOLDOWN
        return vehicle.hp - before

    # ---- bug6: 击杀/助攻计入贡献与积分 ----
    def _add_contrib(self, player: str, kind: str, points: float) -> None:
        record = self.player_contrib.setdefault(
            player, {"kills": 0, "assists": 0, "score": 0.0})
        record[kind] += 1
        record["score"] += points
        self.player_scores[player] = self.player_scores.get(player, 0.0) + points

    def record_vehicle_kill(self, vid: str, assists: list[str] | None = None) -> None:
        vehicle = self.vehicles.get(vid)
        if vehicle is None:
            raise VehicleError("载具不存在")
        self.vehicle_kills[vid] = self.vehicle_kills.get(vid, 0) + 1
        driver = vehicle.driver
        if driver is not None:
            self._add_contrib(driver, "kills", KILL_POINTS)
        for helper in assists or []:
            if helper == driver:
                continue
            self.vehicle_assists[vid] = self.vehicle_assists.get(vid, 0) + 1
            self._add_contrib(helper, "assists", ASSIST_POINTS)

    def get_kill_contribution(self, vid: str) -> float:
        kills = self.vehicle_kills.get(vid, 0)
        assists = self.vehicle_assists.get(vid, 0)
        return kills * KILL_CONTRIBUTION + assists * ASSIST_CONTRIBUTION

    def get_player_contribution(self, player: str) -> dict:
        return self.player_contrib.get(
            player, {"kills": 0, "assists": 0, "score": 0.0})

    def get_player_score(self, player: str) -> float:
        return self.player_scores.get(player, 0.0)

    # ---- bug7: 燃油限制 ----
    def get_fuel_consumption(self, vtype: str) -> float:
        stats = VEHICLE_STATS.get(vtype)
        if stats is None:
            raise VehicleError(f"未知载具类型: {vtype}")
        return stats["fuel_rate"]

    def drive(self, vid: str, duration: float) -> float:
        """行驶消耗燃油, 返回剩余燃油; 耗尽则抛错"""
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive:
            raise VehicleError("载具不存在或已损毁")
        if vehicle.fuel <= 0:
            raise VehicleError("燃油耗尽, 需补给或弃车")
        vehicle.fuel = max(0.0,
                           vehicle.fuel - self.get_fuel_consumption(vehicle.type) * duration)
        if vehicle.fuel <= 0:
            vehicle.abandoned = True
        return vehicle.fuel

    def refuel(self, vid: str, amount: float = 100.0) -> float:
        """补给燃油(消耗团队资源)"""
        vehicle = self.vehicles.get(vid)
        if vehicle is None or not vehicle.alive:
            raise VehicleError("载具不存在或已损毁")
        cost = amount
        if self.team_resources.get(vehicle.team, 0.0) < cost:
            raise VehicleError("补给资源不足")
        self.team_resources[vehicle.team] -= cost
        vehicle.fuel = min(100.0, vehicle.fuel + amount)
        vehicle.abandoned = False
        return vehicle.fuel

    def abandon_vehicle(self, player: str, vid: str, current_time: float) -> None:
        """燃油耗尽时弃车"""
        vehicle = self.vehicles.get(vid)
        if vehicle is None:
            raise VehicleError("载具不存在")
        if vehicle.driver == player:
            vehicle.driver = None
            self.enter_cd[player] = current_time + ENTER_COOLDOWN
        vehicle.abandoned = True
