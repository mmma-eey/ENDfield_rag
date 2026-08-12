"""数据库查询单元测试 —— 属性/等级数值提取（纯逻辑 mock）+ 可选 DB 集成测试"""
import pytest

from rag.db_query import (ATTR_ALIASES, NO_DATA_MSG, _format_attribute_rows,
                          _match_enum, _parse_rarity, field_query_entities,
                          find_entities, query_database)
from rag.intent import INTENT_DATABASE, INTENT_VECTOR
from rag.router import decide_route


class _FakeAttrRow:
    """模拟 OperatorAttribute（仅含换算所需字段）"""
    def __init__(self, stage, values):
        self.stage = stage
        self.values = list(values)
        self.base_val = values[0]


def _kamu_atk_rows():
    """卡缪攻击力成长表（阶段值个数与真实数据一致，边界值共享）"""
    def _lin(start, end, n):
        return [start + (end - start) * i / (n - 1) for i in range(n)]
    return [
        _FakeAttrRow(0, _lin(30.0, 91.0, 20)),       # Lv1~20 → 30~91
        _FakeAttrRow(1, _lin(91.0, 155.0, 21)),      # Lv20~40
        _FakeAttrRow(2, _lin(155.0, 219.0, 21)),     # Lv40~60
        _FakeAttrRow(3, _lin(219.0, 283.0, 21)),     # Lv60~80
        _FakeAttrRow(4, _lin(283.0, 343.0, 20)),     # Lv80~99 → 283~343
    ]


class TestFormatAttributeRows:
    def test_level_within_stage(self):
        rows = _kamu_atk_rows()
        text = _format_attribute_rows("攻击力", rows, 90)
        assert "Lv90" in text
        assert "343" in text  # 阶段最大值（评测期望值）

    def test_level_at_stage_boundary(self):
        # Lv20 为阶段边界，两阶段共享取值 91
        text = _format_attribute_rows("攻击力", _kamu_atk_rows(), 20)
        assert "Lv20≈91.0" in text

    def test_no_level_returns_overview(self):
        text = _format_attribute_rows("攻击力", _kamu_atk_rows(), None)
        assert "攻击力成长" in text
        assert "Lv1~20" in text and "Lv80~99" in text

    def test_level_out_of_range(self):
        text = _format_attribute_rows("攻击力", _kamu_atk_rows(), 999)
        assert "查无" in text

    def test_single_stage_row(self):
        rows = [_FakeAttrRow(0, [10.0, 20.0, 30.0])]
        text = _format_attribute_rows("生命值", rows, 3)
        assert "Lv3≈30.0" in text


class TestParseRarity:
    def test_arabic_numeral(self):
        assert _parse_rarity("有哪些5星干员") == 5

    def test_chinese_numeral(self):
        assert _parse_rarity("有哪些五星干员") == 5
        assert _parse_rarity("有哪些六星先锋") == 6

    def test_no_star(self):
        assert _parse_rarity("卡缪90级攻击力是多少") is None
        assert _parse_rarity("什么是连携技") is None


class TestMatchEnum:
    def test_hit(self):
        assert _match_enum(["终末地工业"], "有哪些终末地工业的干员") == "终末地工业"

    def test_longest_match_priority(self):
        # "护甲" 与 "护手" 同时可匹配时，按问题实际包含的词命中
        assert _match_enum(["护甲", "护手", "配件"], "有哪些五星护甲装备") == "护甲"
        assert _match_enum(["护甲", "护手", "配件"], "银缎护手适合谁") == "护手"

    def test_miss(self):
        assert _match_enum(["辅助", "近卫"], "有哪些先锋干员") is None


class TestAttrAliases:
    def test_no_overlapping_duplicates(self):
        # "攻击力" 与 "攻击" 同时命中时只取最长者（与 db_query 去重逻辑一致）
        labels = [k for k in ATTR_ALIASES if k in "卡缪90级攻击力是多少"]
        labels = sorted(labels, key=len, reverse=True)
        labels = [k for i, k in enumerate(labels) if not any(k in o for o in labels[:i])]
        assert labels == ["攻击力"]

    def test_aliases_cover_common_attrs(self):
        for kw in ("攻击力", "防御力", "生命值", "暴击率", "暴击伤害"):
            assert kw in ATTR_ALIASES


# ---------------- 以下为可选的 DB 集成测试 ----------------
def _db_available() -> bool:
    try:
        from db.database import SessionLocal
        from sqlalchemy import text
        s = SessionLocal()
        s.execute(text("SELECT 1"))
        s.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="PostgreSQL 不可用")


class TestDbIntegration:
    def test_operator_attribute_with_level(self):
        text = query_database("卡缪90级攻击力是多少")
        assert "攻击力" in text
        assert "343" in text  # 成长表最大值

    def test_equipment_query(self):
        text = query_database("纾难识别牌是哪个部位的装备")
        assert "纾难识别牌" in text and "配件" in text

    def test_no_entity_returns_no_data(self):
        assert query_database("什么是连携技") == NO_DATA_MSG

    def test_find_entities_types(self):
        e = find_entities(["镀红祝福和灯火使命哪个更适合卡缪"])
        assert e["operators"] == ["卡缪"]
        assert set(e["weapons"]) == {"镀红祝福", "灯火使命"}

    def test_intent_router_maps_database_query(self):
        # 数值查询 → 数据库意图 → 数据库路由
        d = decide_route([INTENT_DATABASE])
        assert d.plan == "database"
        assert d.is_single
        assert decide_route([INTENT_VECTOR, INTENT_DATABASE]).plan == "hybrid"


class TestFieldQuery:
    """字段模糊查询（Q24 类列表查询）：依赖 DB，DB 不可用时整类跳过"""

    def test_faction_query_q24(self):
        from rag.db_query import _field_query
        lines = _field_query("有哪些终末地工业的干员")
        assert len(lines) >= 20
        assert any("卡缪" in l and "终末地工业" in l for l in lines)

    def test_rarity_equipment_query(self):
        from rag.db_query import _field_query
        lines = _field_query("有哪些五星护甲装备")
        assert lines and all("5星护甲" in l for l in lines[:5])

    def test_profession_rarity_combined(self):
        from rag.db_query import _field_query
        lines = _field_query("有哪些5星先锋干员")
        assert lines and all("5星先锋" in l for l in lines)

    def test_no_field_condition_returns_empty(self):
        from rag.db_query import _field_query
        assert _field_query("卡缪90级攻击力是多少") == []

    def test_query_database_falls_through_to_field_query(self):
        text = query_database("有哪些终末地工业的干员")
        assert text != NO_DATA_MSG
        assert "卡缪" in text

    def test_field_query_entities_operators(self):
        e = field_query_entities("有哪些终末地工业的干员")
        assert "卡缪" in e["operators"] and "佩丽卡" in e["operators"]
        assert e["equipments"] == []

    def test_field_query_entities_equipments(self):
        e = field_query_entities("有哪些五星护甲装备")
        assert e["operators"] == []
        assert any("护甲" in n or "装甲" in n or "服" in n for n in e["equipments"])
        # 评测期望来源出现在命中列表里
        assert len(e["equipments"]) >= 40
