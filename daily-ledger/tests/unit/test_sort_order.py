"""
R-02 單元測試：分類排序功能（sort_order 遷移、排序、reorder、新增排末位）
"""

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import data_manager as dm


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """每個測試使用獨立暫存目錄。"""
    monkeypatch.setattr(dm, "DATA_DIR", tmp_path)
    monkeypatch.setattr(dm, "MAIN_DB", tmp_path / "main_db.csv")
    monkeypatch.setattr(dm, "CATEGORIES_CSV", tmp_path / "categories.csv")


# ===========================================================================
# 遷移邏輯（_migrate_sort_order）
# ===========================================================================


class TestMigrateSortOrder:
    """首次啟動時，若 categories.csv 不含 sort_order 欄位，應自動遷移。"""

    def test_migrate_adds_sort_order_column(self, tmp_path):
        """既有 CSV 無 sort_order 時，init 後應自動補齊。"""
        csv_path = tmp_path / "categories.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["類型", "主類", "次類"])
            w.writerow(["E", "餐飲費", "早餐"])
            w.writerow(["E", "餐飲費", "午餐"])
            w.writerow(["E", "生活雜支", ""])
            w.writerow(["I", "薪資", ""])
        dm.init_data_files()
        rows = dm._read_csv(csv_path)
        assert all("sort_order" in r for r in rows)

    def test_migrate_preserves_original_order(self, tmp_path):
        """遷移後，原有順序不變（以 sort_order 數值遞增表示）。"""
        csv_path = tmp_path / "categories.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["類型", "主類", "次類"])
            w.writerow(["E", "餐飲費", ""])
            w.writerow(["E", "生活雜支", ""])
            w.writerow(["E", "書籍", ""])
        dm.init_data_files()
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["餐飲費", "生活雜支", "書籍"]

    def test_migrate_sub_order_within_main(self, tmp_path):
        """遷移後，次類在同主類內保持原始相對順序。"""
        csv_path = tmp_path / "categories.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["類型", "主類", "次類"])
            w.writerow(["E", "餐飲費", "早餐"])
            w.writerow(["E", "餐飲費", "午餐"])
            w.writerow(["E", "餐飲費", "晚餐"])
        dm.init_data_files()
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs == ["早餐", "午餐", "晚餐"]

    def test_migrate_skipped_if_already_has_sort_order(self, tmp_path):
        """已有 sort_order 的 CSV 不再重新遷移。"""
        csv_path = tmp_path / "categories.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["類型", "主類", "次類", "sort_order"])
            w.writerow(["E", "餐飲費", "", "5"])
            w.writerow(["E", "生活雜支", "", "2"])
        dm.init_data_files()
        cats = dm.get_categories(type_filter="E")
        # 生活雜支 sort_order=2 應排在餐飲費 sort_order=5 前面
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["生活雜支", "餐飲費"]

    def test_migrate_independent_type_ordering(self, tmp_path):
        """遷移時 E 和 I 類型各自獨立計數 sort_order。"""
        csv_path = tmp_path / "categories.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["類型", "主類", "次類"])
            w.writerow(["E", "餐飲費", ""])
            w.writerow(["I", "薪資", ""])
            w.writerow(["E", "生活雜支", ""])
            w.writerow(["I", "其他收入", ""])
        dm.init_data_files()
        e_cats = dm.get_categories(type_filter="E")
        i_cats = dm.get_categories(type_filter="I")
        e_mains = [c["主類"] for c in e_cats if c["次類"] == ""]
        i_mains = [c["主類"] for c in i_cats if c["次類"] == ""]
        assert e_mains == ["餐飲費", "生活雜支"]
        assert i_mains == ["薪資", "其他收入"]


# ===========================================================================
# get_categories 排序
# ===========================================================================


class TestGetCategoriesSorted:
    """GET /api/categories 回傳應依 sort_order 排序。"""

    def test_main_sorted_by_sort_order(self):
        dm.init_data_files()
        dm.add_category("E", "C分類", "")
        dm.add_category("E", "A分類", "")
        dm.add_category("E", "B分類", "")
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        # 依 add 順序排（sort_order 0, 1, 2）
        assert mains == ["C分類", "A分類", "B分類"]

    def test_sub_sorted_within_main(self):
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "晚餐")
        dm.add_category("E", "餐飲費", "早餐")
        dm.add_category("E", "餐飲費", "午餐")
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs == ["晚餐", "早餐", "午餐"]

    def test_main_entry_before_its_subs(self):
        """主類條目（次類=""）應排在其所屬次類前面。"""
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "")
        dm.add_category("E", "餐飲費", "早餐")
        dm.add_category("E", "餐飲費", "午餐")
        cats = dm.get_categories(type_filter="E")
        names = [(c["主類"], c["次類"]) for c in cats]
        assert names[0] == ("餐飲費", "")
        assert names[1] == ("餐飲費", "早餐")
        assert names[2] == ("餐飲費", "午餐")


# ===========================================================================
# reorder_category
# ===========================================================================


class TestReorderCategory:
    """reorder_category 交換相鄰 sort_order 測試。"""

    def _setup_main_cats(self):
        dm.init_data_files()
        dm.add_category("E", "A", "")
        dm.add_category("E", "B", "")
        dm.add_category("E", "C", "")

    def _setup_sub_cats(self):
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "早餐")
        dm.add_category("E", "餐飲費", "午餐")
        dm.add_category("E", "餐飲費", "晚餐")

    # ── 主類排序 ──

    def test_move_main_down(self):
        self._setup_main_cats()
        dm.reorder_category("E", "A", "", "down")
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["B", "A", "C"]

    def test_move_main_up(self):
        self._setup_main_cats()
        dm.reorder_category("E", "C", "", "up")
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["A", "C", "B"]

    def test_move_main_to_first_then_up_raises(self):
        self._setup_main_cats()
        with pytest.raises(ValueError, match="already_first"):
            dm.reorder_category("E", "A", "", "up")

    def test_move_main_to_last_then_down_raises(self):
        self._setup_main_cats()
        with pytest.raises(ValueError, match="already_last"):
            dm.reorder_category("E", "C", "", "down")

    # ── 次類排序 ──

    def test_move_sub_down(self):
        self._setup_sub_cats()
        dm.reorder_category("E", "餐飲費", "早餐", "down")
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs == ["午餐", "早餐", "晚餐"]

    def test_move_sub_up(self):
        self._setup_sub_cats()
        dm.reorder_category("E", "餐飲費", "晚餐", "up")
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs == ["早餐", "晚餐", "午餐"]

    def test_move_sub_first_up_raises(self):
        self._setup_sub_cats()
        with pytest.raises(ValueError, match="already_first"):
            dm.reorder_category("E", "餐飲費", "早餐", "up")

    def test_move_sub_last_down_raises(self):
        self._setup_sub_cats()
        with pytest.raises(ValueError, match="already_last"):
            dm.reorder_category("E", "餐飲費", "晚餐", "down")

    # ── 排序範圍隔離 ──

    def test_sub_reorder_does_not_affect_other_main(self):
        """不同主類的次類排序互不干擾。"""
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "早餐")
        dm.add_category("E", "餐飲費", "午餐")
        dm.add_category("E", "加油", "機車")
        dm.add_category("E", "加油", "汽車")
        dm.reorder_category("E", "餐飲費", "早餐", "down")
        cats = dm.get_categories(type_filter="E")
        gas_subs = [c["次類"] for c in cats if c["主類"] == "加油" and c["次類"] != ""]
        assert gas_subs == ["機車", "汽車"]  # 不受影響

    def test_main_reorder_does_not_affect_other_type(self):
        """E 類型排序不影響 I 類型。"""
        dm.init_data_files()
        dm.add_category("E", "A", "")
        dm.add_category("E", "B", "")
        dm.add_category("I", "薪資", "")
        dm.add_category("I", "其他", "")
        dm.reorder_category("E", "A", "", "down")
        i_cats = dm.get_categories(type_filter="I")
        i_mains = [c["主類"] for c in i_cats if c["次類"] == ""]
        assert i_mains == ["薪資", "其他"]

    # ── 邊界 ──

    def test_reorder_not_found_raises(self):
        dm.init_data_files()
        dm.add_category("E", "A", "")
        with pytest.raises(ValueError, match="not_found"):
            dm.reorder_category("E", "不存在", "", "up")

    def test_reorder_invalid_direction_raises(self):
        dm.init_data_files()
        dm.add_category("E", "A", "")
        with pytest.raises(ValueError, match="invalid_direction"):
            dm.reorder_category("E", "A", "", "left")

    def test_multiple_reorder_round_trip(self):
        """連續 down → down → up → up 回到原始。"""
        self._setup_main_cats()
        dm.reorder_category("E", "A", "", "down")  # B, A, C
        dm.reorder_category("E", "A", "", "down")  # B, C, A
        dm.reorder_category("E", "A", "", "up")  # B, A, C
        dm.reorder_category("E", "A", "", "up")  # A, B, C
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["A", "B", "C"]


# ===========================================================================
# add_category 自動 sort_order
# ===========================================================================


class TestAddCategorySortOrder:
    """新增分類應自動排在同範圍末位。"""

    def test_new_main_appended_last(self):
        dm.init_data_files()
        dm.add_category("E", "A", "")
        dm.add_category("E", "B", "")
        dm.add_category("E", "C", "")
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains[-1] == "C"

    def test_new_sub_appended_last(self):
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "早餐")
        dm.add_category("E", "餐飲費", "午餐")
        dm.add_category("E", "餐飲費", "晚餐")
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs[-1] == "晚餐"

    def test_add_after_reorder_goes_to_end(self):
        """排序後新增的分類仍在末位。"""
        dm.init_data_files()
        dm.add_category("E", "A", "")
        dm.add_category("E", "B", "")
        dm.reorder_category("E", "B", "", "up")  # B, A
        dm.add_category("E", "C", "")
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["B", "A", "C"]


# ===========================================================================
# ensure_categories sort_order（匯入用）
# ===========================================================================


class TestEnsureCategoriesSortOrder:
    """批次匯入新增的分類也應有正確的 sort_order。"""

    def test_ensure_categories_has_sort_order(self):
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "")
        dm.ensure_categories(
            [
                {"類型": "E", "主類": "生活雜支", "次類": ""},
                {"類型": "E", "主類": "交通", "次類": ""},
            ]
        )
        cats = dm.get_categories(type_filter="E")
        mains = [c["主類"] for c in cats if c["次類"] == ""]
        assert mains == ["餐飲費", "生活雜支", "交通"]

    def test_ensure_categories_sub_sort_order(self):
        dm.init_data_files()
        dm.add_category("E", "餐飲費", "早餐")
        dm.ensure_categories(
            [
                {"類型": "E", "主類": "餐飲費", "次類": "午餐"},
                {"類型": "E", "主類": "餐飲費", "次類": "晚餐"},
            ]
        )
        cats = dm.get_categories(type_filter="E")
        subs = [c["次類"] for c in cats if c["次類"] != ""]
        assert subs == ["早餐", "午餐", "晚餐"]
