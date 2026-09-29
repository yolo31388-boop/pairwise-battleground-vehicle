"""战场载具与攻城系统 - 红态测试"""
import pytest, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from battleground.vehicle import VehicleSystem, Vehicle

class TestVehicleLimit:
    def test_vehicle_count_limited_by_team(self):
        vs = VehicleSystem()
        limit = vs.get_vehicle_limit(team_size=10)
        assert limit < 20

class TestEnterCooldown:
    def test_vehicle_entry_has_cooldown(self):
        vs = VehicleSystem()
        vs.enter_cd["p1"] = 100.0
        assert vs.can_enter_vehicle("p1", 50.0) == False
        assert vs.can_enter_vehicle("p1", 150.0) == True

class TestDeployTime:
    def test_siege_vehicle_needs_deploy_time(self):
        vs = VehicleSystem()
        vs.vehicles["v1"] = Vehicle("v1", "siege", deploy_time=100.0)
        assert vs.is_deployed("v1", 50.0) == False
        assert vs.is_deployed("v1", 150.0) == True

class TestVehicleHpByType:
    def test_tank_has_more_hp_than_scout(self):
        vs = VehicleSystem()
        hp_tank = vs.get_vehicle_hp("tank")
        hp_scout = vs.get_vehicle_hp("scout")
        assert hp_tank > hp_scout

class TestRepairCooldown:
    def test_repair_has_cooldown(self):
        vs = VehicleSystem()
        vs.repair_cd["v1"] = 100.0
        assert vs.can_repair("v1", 50.0) == False

class TestKillContribution:
    def test_vehicle_kills_count_toward_contribution(self):
        vs = VehicleSystem()
        vs.vehicles["v1"] = Vehicle("v1", "tank")
        # 应该有击杀记录
        assert hasattr(vs, "vehicle_kills")
        vs.vehicle_kills = {"v1": 5}
        contrib = vs.get_kill_contribution("v1")
        assert contrib > 0

class TestFuelConsumption:
    def test_vehicle_consumes_fuel(self):
        vs = VehicleSystem()
        consumption = vs.get_fuel_consumption("tank")
        assert consumption > 0
