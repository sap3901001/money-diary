#!/usr/bin/env python3
"""MyAB 記帳資料匯出工具 — 將 .abd 或 .mbu 檔案匯出為 CSV"""

import csv
import os
import struct
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(SCRIPT_DIR, 'source')
TARGET_DIR = os.path.join(SCRIPT_DIR, 'target')

REC_SIZE = 284          # Main.abd 每筆記錄大小
MAIN1_HEADER = 104      # Main1.abd 標頭大小
MAIN1_REC = 204         # Main1.abd 每筆記錄大小
MAIN1_NOTE_OFFSET = 104 # Main1.abd 記錄內備註起始位置

CSV_HEADER = ['日期', '類型', '類別主類', '類別次類', '帳戶', '金額', '明細', '備註']

ACCT_REC_SIZE = 276     # Accounts.abd 每筆記錄大小
ACCT_NAME_LEN = 32      # 名稱欄位長度
TYPE_MAP = {'A': '資產', 'L': '負債', 'I': '收入', 'E': '支出', 'Equity': '權益'}
ACCT_CSV_HEADER = ['類型', '類型名稱', '階層', '主類', '次類']


# ── 金額解碼 ──────────────────────────────────────────────

def decode_amount(b4: bytes) -> int:
    """LE 4 bytes → BE top4 of double(TWD*100) → TWD 整數"""
    be_top4 = bytes([b4[3], b4[2], b4[1], b4[0]])
    value = struct.unpack('>d', be_top4 + b'\x00\x00\x00\x00')[0] / 100
    return round(value)


# ── Big5 解碼輔助 ─────────────────────────────────────────

def decode_big5(data: bytes) -> str:
    return data.rstrip(b'\x00\x20').decode('big5', errors='replace')


# ── 類別碼分割 ────────────────────────────────────────────

def split_category(cat_str: str):
    """將 '主類.次類' 分割為 (主類, 次類)"""
    if '.' in cat_str:
        parts = cat_str.split('.', 1)
        return parts[0], parts[1]
    return cat_str, ''


# ── DataBase 版 Main.abd 解析 ─────────────────────────────

def parse_main_db(data: bytes) -> list:
    """解析 DataBase 版 Main.abd，回傳 (記錄列表, 原始索引列表)"""
    records = []
    indices = []  # 記錄每筆在 Main.abd 中的原始索引（用於對齊備註）
    count = len(data) // REC_SIZE
    for i in range(count):
        rec = data[i * REC_SIZE:(i + 1) * REC_SIZE]
        # 跳過空白記錄
        if rec == b'\x00' * REC_SIZE or rec == b'\x20' * REC_SIZE:
            continue
        date = rec[0x00:0x0A].decode('ascii', errors='replace').strip()
        rtype = rec[0x0A:0x0B].decode('ascii', errors='replace').strip()
        if rtype not in ('E', 'I', 'A', 'L'):
            continue
        cat = decode_big5(rec[0x0C:0x28])
        acct = decode_big5(rec[0x28:0x30]).strip()
        amount = decode_amount(rec[0x50:0x54])
        if rtype == 'E':
            amount = -amount
        detail = decode_big5(rec[0x54:0x112])
        main_cat, sub_cat = split_category(cat)
        records.append([date, rtype, main_cat, sub_cat, acct, amount, detail])
        indices.append(i)
    return records, indices


# ── Main1.abd 備註解析 ────────────────────────────────────

def parse_main1_notes(data: bytes) -> list:
    """解析 Main1.abd，回傳備註列表（note[i] 對應 Main.abd rec[i+1]）"""
    notes = []
    body = data[MAIN1_HEADER:]
    count = len(body) // MAIN1_REC
    for i in range(count):
        rec = body[i * MAIN1_REC:(i + 1) * MAIN1_REC]
        note = rec[MAIN1_NOTE_OFFSET:].rstrip(b'\x00\x20').decode('big5', errors='replace')
        note = note.strip('\x00').strip()
        notes.append(note)
    return notes


# ── Accounts.abd 科目解析 ─────────────────────────────────

def parse_accounts(data: bytes) -> list:
    """解析 Accounts.abd，回傳科目列表 [[類型, 類型名稱, 階層, 主類, 次類], ...]"""
    accounts = []
    # 以 ACCT_REC_SIZE 切割，最後不足一筆的也處理（名稱欄位仍完整）
    total = len(data)
    i = 0
    while i < total:
        end = min(i + ACCT_REC_SIZE, total)
        rec = data[i:end]
        i = end
        # 跳過空白記錄
        name_field = rec[:ACCT_NAME_LEN] if len(rec) >= ACCT_NAME_LEN else rec
        name = decode_big5(name_field)
        if not name:
            continue
        # 解析 TYPE-主類.次類 格式
        if '-' in name:
            typ = name.split('-', 1)[0]
            cat_part = name.split('-', 1)[1]
            main_cat, sub_cat = split_category(cat_part)
            level = '次類' if sub_cat else '主類'
        else:
            # Equity 等無 '-' 分隔的條目
            typ = name.strip()
            main_cat = typ
            sub_cat = ''
            level = '主類'
        type_name = TYPE_MAP.get(typ, typ)
        accounts.append([typ, type_name, level, main_cat, sub_cat])
    return accounts


def write_accounts_csv(accounts: list, output_path: str):
    """將科目設定寫入 CSV（UTF-8-BOM）"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(ACCT_CSV_HEADER)
        for row in accounts:
            writer.writerow(row)
    print(f'  已匯出 {len(accounts)} 筆科目 → {output_path}')


# ── .mbu 索引解析 ─────────────────────────────────────────

def parse_mbu_index(data: bytes) -> dict:
    """解析 .mbu 索引，回傳 {檔名: (offset, size)} dict"""
    files = {}
    # 找第一個 \x01（第一個檔案條目在 header 行末尾）
    first_sep = data.find(b'\x01')
    if first_sep == -1:
        return files

    # 從 \x01 往前搜尋路徑起始位置：找到最近的空格後第一個非空格字元
    # 格式: username[spaces][version][spaces]filepath\x01size\r\n
    line_start = first_sep - 1
    while line_start > 0 and data[line_start] != 0x20:
        line_start -= 1
    line_start += 1  # 跳過空格，指向路徑第一個字元

    # 從 line_start 開始解析所有條目
    pos = line_start
    entries = []
    while pos < len(data):
        sep = data.find(b'\x01', pos)
        if sep == -1:
            break
        filepath = data[pos:sep]
        end = data.find(b'\r\n', sep)
        if end == -1:
            break
        # 路徑合理性驗證：必須含 .abd、.lst、.pwd 等副檔名或 \ 路徑分隔符
        fname = filepath.decode('ascii', errors='replace')
        if not any(ext in fname.lower() for ext in ('.abd', '.lst', '.pwd', '\\')):
            break
        size_str = data[sep + 1:end].decode('ascii', errors='replace').strip()
        try:
            size = int(size_str)
        except ValueError:
            break
        entries.append((fname, size))
        pos = end + 2

    # 計算偏移（索引結束後開始）
    index_end = pos
    offset = index_end
    for fname, size in entries:
        # 只保留檔名部分（去除目錄路徑）
        basename = fname.rsplit('\\', 1)[-1] if '\\' in fname else fname
        files[basename] = (offset, size)
        offset += size

    return files


# ── CSV 寫入 ──────────────────────────────────────────────

def write_csv(records: list, indices: list, notes: list, output_path: str):
    """將記錄寫入 CSV（UTF-8-BOM）
    notes[n] 對應 Main.abd rec[n+1]，因此 rec[i] 的備註為 notes[i-1]
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)
        for rec, orig_idx in zip(records, indices):
            note_idx = orig_idx - 1  # note[n] → rec[n+1]
            note = notes[note_idx] if 0 <= note_idx < len(notes) else ''
            writer.writerow(rec + [note])
    print(f'  已匯出 {len(records)} 筆記錄 → {output_path}')


# ── 模式偵測 ──────────────────────────────────────────────

def detect_mode():
    """掃描 source/ 目錄，回傳 ('db', ...) 或 ('mbu', [...])"""
    if not os.path.isdir(SOURCE_DIR):
        print(f'錯誤：找不到 source 目錄：{SOURCE_DIR}')
        sys.exit(1)

    files = os.listdir(SOURCE_DIR)
    if not files:
        print(f'錯誤：source 目錄為空，請放入 .mbu 或 Main.abd 檔案')
        sys.exit(1)

    for f in sorted(files):
        ext = os.path.splitext(f)[1].lower()
        if ext == '.mbu':
            mbu_files = sorted([x for x in files if x.lower().endswith('.mbu')])
            return 'mbu', mbu_files
        elif ext == '.abd':
            return 'db', None

    print(f'錯誤：source 目錄中找不到 .mbu 或 .abd 檔案')
    sys.exit(1)


# ── 主程式 ────────────────────────────────────────────────

def main():
    print('MyAB 記帳資料匯出工具')
    print('=' * 40)

    mode, mbu_files = detect_mode()

    if mode == 'db':
        print(f'模式：DataBase（直接讀取 .abd）')
        main_path = os.path.join(SOURCE_DIR, 'Main.abd')
        if not os.path.isfile(main_path):
            print(f'錯誤：找不到 {main_path}')
            sys.exit(1)

        with open(main_path, 'rb') as f:
            main_data = f.read()
        records, indices = parse_main_db(main_data)
        print(f'  Main.abd：{len(main_data)} bytes，解析 {len(records)} 筆交易')

        # 嘗試讀取 Main1.abd
        notes = []
        main1_path = os.path.join(SOURCE_DIR, 'Main1.abd')
        if os.path.isfile(main1_path):
            with open(main1_path, 'rb') as f:
                main1_data = f.read()
            notes = parse_main1_notes(main1_data)
            print(f'  Main1.abd：{len(main1_data)} bytes，解析 {len(notes)} 筆備註')
        else:
            print(f'  Main1.abd：未找到，備註欄留空')

        output_path = os.path.join(TARGET_DIR, 'transactions.csv')
        write_csv(records, indices, notes, output_path)

        # 嘗試讀取 Accounts.abd（科目設定）
        acct_path = os.path.join(SOURCE_DIR, 'Accounts.abd')
        if os.path.isfile(acct_path):
            with open(acct_path, 'rb') as f:
                acct_data = f.read()
            accounts = parse_accounts(acct_data)
            print(f'  Accounts.abd：{len(acct_data)} bytes，解析 {len(accounts)} 筆科目')
            acct_output = os.path.join(TARGET_DIR, 'accounts.csv')
            write_accounts_csv(accounts, acct_output)
        else:
            print(f'  Accounts.abd：未找到，跳過科目匯出')

    elif mode == 'mbu':
        print(f'模式：.mbu 備份檔（共 {len(mbu_files)} 個）')
        for mbu_name in mbu_files:
            print(f'\n處理：{mbu_name}')
            mbu_path = os.path.join(SOURCE_DIR, mbu_name)
            with open(mbu_path, 'rb') as f:
                mbu_data = f.read()

            index = parse_mbu_index(mbu_data)
            if not index:
                print(f'  警告：無法解析索引，跳過')
                continue

            # 提取 Main.abd
            if 'Main.abd' not in index:
                print(f'  警告：索引中找不到 Main.abd，跳過')
                continue
            main_offset, main_size = index['Main.abd']
            main_data = mbu_data[main_offset:main_offset + main_size]
            records, indices = parse_main_db(main_data)
            print(f'  Main.abd：{main_size} bytes，解析 {len(records)} 筆交易')

            # 提取 Main1.abd（備註）
            notes = []
            if 'Main1.abd' in index:
                m1_offset, m1_size = index['Main1.abd']
                main1_data = mbu_data[m1_offset:m1_offset + m1_size]
                notes = parse_main1_notes(main1_data)
                print(f'  Main1.abd：{m1_size} bytes，解析 {len(notes)} 筆備註')
            else:
                print(f'  Main1.abd：索引中未找到，備註欄留空')

            stem = os.path.splitext(mbu_name)[0]
            output_path = os.path.join(TARGET_DIR, f'backup_{stem}.csv')
            write_csv(records, indices, notes, output_path)

            # 提取 Accounts.abd（科目設定）
            if 'Accounts.abd' in index:
                a_offset, a_size = index['Accounts.abd']
                acct_data = mbu_data[a_offset:a_offset + a_size]
                accounts = parse_accounts(acct_data)
                print(f'  Accounts.abd：{a_size} bytes，解析 {len(accounts)} 筆科目')
                acct_output = os.path.join(TARGET_DIR, f'backup_{stem}_accounts.csv')
                write_accounts_csv(accounts, acct_output)
            else:
                print(f'  Accounts.abd：索引中未找到，跳過科目匯出')

    print('\n完成！')


if __name__ == '__main__':
    main()
