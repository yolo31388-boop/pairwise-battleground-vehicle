"""战场载具与攻城系统 - 含7个bug"""
from dataclasses import dataclass, field

@dataclass
class Vehicle:
    vid: str
    type: str  # tank/scout/siege
    hp: float = 100
    max_hp: float = 100
    fuel: float = 100  # bug7: 无燃油限制
    deploy_time: float = 0  # bug3: 无架设时间

class VehicleSystem:
    def __init__(self):
        self.vehicles: dict[str, Vehicle] = {}
        self.team_vehicles: dict[str, list] = {}  # bug1: 无数量限制
        self.enter_cd: dict[str, float] = {}  # bug2: 无操作冷却
        self.repair_cd: dict[str, float] = {}  # bug5: 无维修冷却

    def get_vehicle_limit(self, team_size: int) -> int:
        # bug1: 无数量限制
        return 999

    def can_enter_vehicle(self, player: str, current_time: float) -> bool:
        # bug2: 无冷却
        return True

    def is_deployed(self, vid: str, current_time: float) -> bool:
        # bug3: 无架设时间
        return True

    def get_vehicle_hp(self, vtype: str) -> float:
        # bug4: 固定血量
        return 100.0

    def can_repair(self, vid: str, current_time: float) -> bool:
        # bug5: 无冷却瞬间修满
        return True

    def get_kill_contribution(self, vid: str) -> float:
        # bug6: 载具击杀不算贡献
        return 0.0

    def get_fuel_consumption(self, vtype: str) -> float:
        # bug7: 无燃油消耗
        return 0.0
