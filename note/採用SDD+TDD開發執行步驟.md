# 採用 SDD + TDD 開發執行步驟

> 本文件說明如何以 **Subagent-Driven Development（SDD）** 搭配 **Test-Driven Development（TDD）** 模式，
> 在 Claude Code 環境下將 SA 設計藍圖轉化為可執行的開發任務，並完整記錄 QA 文件與開發 Log 的產出與存放位置。

---

## 目錄

1. [前置條件：Skills 安裝檢查](#1-前置條件skills-安裝檢查)
2. [必要交付文件清單](#2-必要交付文件清單)
3. [整體工作流程概覽](#3-整體工作流程概覽)
4. [階段一：環境準備](#4-階段一環境準備)
5. [階段二：計畫產製（SA 藍圖 → 實作計畫）](#5-階段二計畫產製sa-藍圖--實作計畫)
6. [階段三：SDD 執行（Orchestrator 派工）](#6-階段三sdd-執行orchestrator-派工)
7. [階段四：QA 測試（qa-orchestra）](#7-階段四qa-測試qa-orchestra)
8. [階段五：開發收尾](#8-階段五開發收尾)
9. [產出文件存放位置總覽](#9-產出文件存放位置總覽)
10. [常見問題與注意事項](#10-常見問題與注意事項)

---

## 1. 前置條件：Skills 安裝檢查

開始開發前，請確認以下 Skills 均已安裝。

### 1.1 執行檢查指令

在 Claude Code 終端機輸入：

```bash
claude plugin list
```

### 1.2 必要 Skills 對照表

| 優先級 | Skill 名稱 | 用途 | 所屬 Marketplace |
|:---:|---|---|---|
| 必要 | `writing-plans` | 將 SA 藍圖拆解為可執行任務計畫 | superpowers-marketplace |
| 必要 | `subagent-driven-development` | Orchestrator 派工核心（SDD 主流程） | superpowers-marketplace |
| 必要 | `test-driven-development` | 強制 TDD 流程（先測試後實作） | superpowers-marketplace |
| 必要 | `requesting-code-review` | 每個 Task 完成後的 Code Review 派工 | superpowers-marketplace |
| 必要 | `receiving-code-review` | 正確處理 Code Review 回饋 | superpowers-marketplace |
| 必要 | `verification-before-completion` | 完成前的驗證門禁 | superpowers-marketplace |
| 必要 | `finishing-a-development-branch` | 開發完成後的 branch 整合流程 | superpowers-marketplace |
| 建議 | `using-git-worktrees` | 隔離的 Git 工作空間 | superpowers-marketplace |
| 建議 | `dispatching-parallel-agents` | 多個獨立任務同時派工 | superpowers-marketplace |
| 建議 | `qa-orchestra` | 完整 QA 測試 Pipeline | claude-code-workflows |
| 建議 | `documentation-generation` | API 文件、架構圖自動產製 | claude-code-workflows |
| 建議 | `episodic-memory` | 跨 session 開發記憶與決策追蹤 | superpowers-marketplace |

### 1.3 缺少 Skill 時的安裝指令

```bash
claude plugin install <skill-名稱>
```

範例：

```bash
claude plugin install writing-plans
claude plugin install qa-orchestra
```

---

## 2. 必要交付文件清單

### 2.1 開發啟動前（Input 文件）

| 文件 | 負責人 | 必要性 | 說明 |
|---|---|:---:|---|
| SA 設計藍圖 | SA / 架構師 | 必要 | 功能需求、API 設計、資料結構、AC（驗收條件） |
| Tech Stack 說明 | SA / Lead Dev | 必要 | 語言、框架、測試工具（如 Vitest、pytest、Jest） |
| Git Branch 規範 | 專案規範 | 建議 | 命名規則，如 `feature/ISSUE-001-feature-name` |
| CONTEXT.md | QA / Dev | QA必要 | 提供給 qa-orchestra 使用的專案環境說明 |

### 2.2 開發過程產出（Output 文件）

| 文件 | 產製工具 | 存放路徑 |
|---|---|---|
| 實作計畫書 | `writing-plans` | `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` |
| QA 執行計畫 | `qa-orchestra @orchestrator` | `qa-output/plan.md` |
| 環境狀態報告 | `qa-orchestra @environment-manager` | `qa-output/environment-status.md` |
| 功能審查報告 | `qa-orchestra @functional-reviewer` | `qa-output/functional-review.md` |
| 測試情境設計 | `qa-orchestra @test-scenario-designer` | `qa-output/test-scenarios.md` |
| 瀏覽器驗證報告 | `qa-orchestra @browser-validator` | `qa-output/browser-validation.md` |
| Bug 報告 | `qa-orchestra @bug-reporter` | `qa-output/bug-reports.md` |
| 自動化測試腳本 | `qa-orchestra @automation-writer` | `qa-output/automation/` |
| 手動驗證報告 | `qa-orchestra @manual-validator` | `qa-output/validation-report.md` |
| 版本分析報告 | `qa-orchestra @release-analyzer` | `qa-output/release-analysis.md` |
| 受影響測試清單 | `qa-orchestra @smart-test-selector` | `qa-output/test-selection.md` |
| API / 架構文件 | `documentation-generation` | `docs/` 或 `qa-output/docs/`（依設定） |

---

## 3. 整體工作流程概覽

```
SA 設計藍圖
    │
    ▼
[階段一] 環境準備
    │  建立 feature branch + Git worktree
    │  建立 context/CONTEXT.md（供 QA 使用）
    ▼
[階段二] 計畫產製
    │  writing-plans skill
    │  → docs/superpowers/plans/YYYY-MM-DD-feature.md
    ▼
[階段三] SDD 執行（逐 Task 派工）
    │
    │  ┌── Implementer Subagent（TDD 模式）
    │  │     1. 寫失敗測試
    │  │     2. 確認測試失敗
    │  │     3. 寫最小實作
    │  │     4. 確認測試通過
    │  │     5. Commit
    │  │
    │  ├── Spec Reviewer Subagent
    │  │     確認實作符合 SA 規格
    │  │
    │  └── Code Quality Reviewer Subagent
    │        確認程式品質（單一職責、可測試性）
    │
    ▼（所有 Task 完成）
[階段四] QA 測試（qa-orchestra）
    │
    │  environment-manager → functional-reviewer
    │  test-scenario-designer → browser-validator
    │  bug-reporter / automation-writer
    │
    ▼（QA 通過）
[階段五] 開發收尾
       finishing-a-development-branch skill
       → Merge / PR / 清理 worktree
```

---

## 4. 階段一：環境準備

### 4.1 建立隔離工作空間

對 Claude Code 說：

```
請用 using-git-worktrees 建立 feature branch，分支名稱：feature/ISSUE-001-feature-name
```

Claude 會執行：

```bash
git worktree add .worktrees/feature-name -b feature/ISSUE-001-feature-name
```

### 4.2 建立 CONTEXT.md（QA 必要）

在專案根目錄建立 `context/CONTEXT.md`，填入以下資訊：

```markdown
# Project Context

## Stack
- Frontend: React + TypeScript + Vite
- Backend: Node.js / Python（填入實際技術）
- Test framework: Vitest / Jest / pytest（填入實際工具）
- E2E: Playwright / Cypress（填入實際工具）

## Start Commands
- Frontend: `npm run dev`（Port: 5173）
- Backend: `npm run start`（Port: 3000）

## Repo Structure
- Frontend: ./frontend
- Backend: ./backend

## Preferences
- Language: zh-TW（繁體中文）
- Bug severity: Critical / High / Medium / Low
- AC format: Given-When-Then
```

---

## 5. 階段二：計畫產製（SA 藍圖 → 實作計畫）

### 5.1 啟動方式

將 SA 藍圖貼給 Claude，並說：

```
我有一份 SA 設計藍圖，請用 writing-plans 產製實作計畫。

Tech Stack：React + TypeScript（Frontend）、Node.js（Backend）
測試工具：Vitest（單元測試）、Playwright（E2E）

[貼上 SA 藍圖完整內容]
```

### 5.2 Claude 的產出

Claude 會宣告：「I'm using the writing-plans skill to create the implementation plan.」

並產生計畫檔至：

```
docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md
```

### 5.3 計畫檔格式範例

```markdown
# [功能名稱] Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** 一句話說明此功能目標
**Architecture:** 2-3 句說明技術架構
**Tech Stack:** React, TypeScript, Vitest, Playwright

---

### Task 1: [元件名稱]

**Files:**
- Create: `src/components/Feature.tsx`
- Test:   `src/components/Feature.test.tsx`

- [ ] Step 1: 寫失敗測試
- [ ] Step 2: 確認測試失敗（`npm test Feature.test.tsx`）
- [ ] Step 3: 寫最小實作
- [ ] Step 4: 確認測試通過
- [ ] Step 5: Commit

### Task 2: ...
```

### 5.4 確認計畫

閱讀計畫後，若無問題，說：

```
計畫確認，請用 subagent-driven-development 開始執行。
```

---

## 6. 階段三：SDD 執行（Orchestrator 派工）

### 6.1 Orchestrator 工作循環

Claude 作為 Orchestrator，針對計畫中的每個 Task 依序執行以下循環：

```
┌──────────────────────────────────────────────────────────┐
│  Task N 執行循環                                          │
│                                                          │
│  Step 1：派出 Implementer Subagent                        │
│          ─ 提供完整 Task 文字 + 場景說明                   │
│          ─ 指示使用 test-driven-development              │
│          ─ 等待 Subagent 回報狀態                         │
│                                                          │
│  Step 2：處理 Implementer 回報狀態                        │
│          ─ DONE：進入 Step 3                             │
│          ─ DONE_WITH_CONCERNS：評估後進入 Step 3          │
│          ─ NEEDS_CONTEXT：提供補充資訊，重新派工            │
│          ─ BLOCKED：診斷問題，拆解或升級 Model             │
│                                                          │
│  Step 3：派出 Spec Reviewer Subagent                     │
│          ─ 確認實作符合 SA 規格（不多不少）                 │
│          ─ ✅ 通過 → Step 4                              │
│          ─ ❌ 未通過 → Implementer 修正 → 重新審查         │
│                                                          │
│  Step 4：派出 Code Quality Reviewer Subagent             │
│          ─ 確認程式品質（單一職責、可測試性、命名）          │
│          ─ ✅ 通過 → 標記 Task 完成 → Task N+1            │
│          ─ ❌ 未通過 → Implementer 修正 → 重新審查         │
└──────────────────────────────────────────────────────────┘
```

### 6.2 Implementer TDD 作業流程

每個 Implementer Subagent 強制遵守 TDD 鐵律：

```
❌ 禁止在沒有失敗測試的情況下寫任何實作程式碼
```

TDD 步驟：

```
1. 寫失敗測試（Red）
   ─ 對應 AC 的最小可驗證行為
   ─ 執行測試，確認是 FAIL

2. 寫最小實作（Green）
   ─ 只寫讓測試通過的最小程式碼
   ─ 執行測試，確認是 PASS

3. 重構（Refactor）
   ─ 在測試保護下清理程式碼
   ─ 再次確認測試 PASS

4. Commit
   ─ git add <specific-files>
   ─ git commit -m "feat: 描述功能"
```

### 6.3 平行派工（獨立任務）

若多個 Task 之間無依賴關係，使用 `dispatching-parallel-agents`：

```
對 Claude 說：
「Task 3、Task 4、Task 5 彼此獨立，
 請用 dispatching-parallel-agents 同時派工。」
```

---

## 7. 階段四：QA 測試（qa-orchestra）

### 7.1 前置條件

- 應用程式必須可在本機啟動（feature branch 版本）
- `context/CONTEXT.md` 必須已填寫完整
- 若使用 `@browser-validator`，需已安裝 Chrome MCP

### 7.2 QA Pipeline 執行方式

#### 方式 A：全流程（Orchestrator 自動協調）

```
Run @orchestrator for PR #42
```

#### 方式 B：按需單獨執行

| 情境 | 指令 |
|---|---|
| 確認 PR 是否符合 AC | `@functional-reviewer Compare this diff against these ACs: [貼上 AC]` |
| 設計測試情境 | `@test-scenario-designer Generate scenarios for these ACs: [貼上 AC]` |
| 找出受影響的測試 | `@smart-test-selector Which existing tests are affected by this diff?` |
| 瀏覽器實際驗證 | `@environment-manager checkout feature/xxx and start the app` → `@browser-validator validate scenarios` |
| 產出 Bug 報告 | `@bug-reporter read qa-output/functional-review.md and create bug reports` |
| 產出自動化測試 | `@automation-writer read qa-output/test-scenarios.md and generate Playwright tests` |
| 分析版本差異 | `@release-analyzer analyze the diff between v1.0 and HEAD` |

### 7.3 QA Pipeline 自動執行流程

```
1. environment-manager
   └─ Checkout feature branch、安裝依賴、啟動 App、健康檢查
   └─ 輸出：qa-output/environment-status.md

2. （平行執行）
   ├─ functional-reviewer
   │   └─ 對照 AC 審查 Diff → qa-output/functional-review.md
   └─ test-scenario-designer
       └─ 設計測試情境 → qa-output/test-scenarios.md

3. browser-validator（需 Chrome MCP）
   └─ 對執行中的 App 進行實際瀏覽器驗證
   └─ 輸出：qa-output/browser-validation.md
         qa-output/screenshots/（截圖證據）

4. （條件性平行執行）
   ├─ bug-reporter（若 Step 2/3 發現 Gap）
   │   └─ 輸出：qa-output/bug-reports.md
   └─ automation-writer
       └─ 輸出：qa-output/automation/*.spec.ts
```

### 7.4 QA 輸出文件格式

每份 QA 文件開頭均包含機器可讀的 JSON 區塊：

````
```json qa-orchestra
{
  "agent": "functional-reviewer",
  "status": "GAPS",
  "verdict": "needs-browser-validation"
}
```
````

後接可直接貼至 GitHub Issues / Jira / Linear 的 Markdown 內容。

---

## 8. 階段五：開發收尾

### 8.1 啟動收尾流程

所有 Task 完成、QA 通過後，說：

```
請用 finishing-a-development-branch 完成這次開發。
```

### 8.2 收尾流程

Claude 會：

1. **驗證測試全數通過**（若有失敗，停止並回報）
2. **偵測工作環境**（一般 repo / worktree）
3. **提供整合選項**：

```
Implementation complete. What would you like to do?

1. Merge back to main locally
2. Push and create a Pull Request
3. Keep the branch as-is（稍後處理）
4. Discard this work
```

4. **執行選擇**，並清理 worktree（選項 1、4）

### 8.3 建立 PR 時的自動產出

選擇選項 2 時，Claude 自動產出：

```markdown
## Summary
- 功能 A：實作說明
- 功能 B：實作說明

## Test Plan
- [ ] 測試項目 1
- [ ] 測試項目 2

🤖 Generated with Claude Code
```

---

## 9. 產出文件存放位置總覽

### 9.1 開發文件（Dev Log）

| 文件 | 路徑 | 產製時機 |
|---|---|---|
| 實作計畫書 | `docs/superpowers/plans/YYYY-MM-DD-<feature>.md` | 階段二：計畫產製 |
| Git Commit Log | `git log`（版本控制） | 每個 Task 完成時 |
| PR 描述 | GitHub / GitLab PR | 階段五：開發收尾 |

### 9.2 QA 文件

| 文件 | 路徑 | 產製 Agent |
|---|---|---|
| QA 執行計畫 | `qa-output/plan.md` | `@orchestrator` |
| 環境狀態報告 | `qa-output/environment-status.md` | `@environment-manager` |
| 功能審查報告 | `qa-output/functional-review.md` | `@functional-reviewer` |
| 測試情境設計 | `qa-output/test-scenarios.md` | `@test-scenario-designer` |
| 瀏覽器驗證報告 | `qa-output/browser-validation.md` | `@browser-validator` |
| 瀏覽器截圖 | `qa-output/screenshots/` | `@browser-validator` |
| Bug 報告 | `qa-output/bug-reports.md` | `@bug-reporter` |
| 手動驗證報告 | `qa-output/validation-report.md` | `@manual-validator` |
| 受影響測試清單 | `qa-output/test-selection.md` | `@smart-test-selector` |
| 版本分析報告 | `qa-output/release-analysis.md` | `@release-analyzer` |
| 自動化測試腳本 | `qa-output/automation/` | `@automation-writer` |

### 9.3 目錄結構示意圖

```
project-root/
│
├── docs/
│   └── superpowers/
│       └── plans/
│           └── 2026-05-07-feature-name.md   ← 實作計畫書
│
├── context/
│   ├── CONTEXT.md                           ← QA 專案環境說明
│   └── annotations/                         ← QA 自動學習的專案知識
│       ├── services.md
│       ├── test-patterns.md
│       ├── environments.md
│       └── domain.md
│
├── qa-output/                               ← 所有 QA 文件
│   ├── plan.md
│   ├── environment-status.md
│   ├── functional-review.md
│   ├── test-scenarios.md
│   ├── browser-validation.md
│   ├── bug-reports.md
│   ├── validation-report.md
│   ├── test-selection.md
│   ├── release-analysis.md
│   ├── screenshots/
│   └── automation/
│       └── feature.spec.ts
│
└── src/                                     ← 實作程式碼
    └── ...（含測試檔）
```

---

## 10. 常見問題與注意事項

### 10.1 Skills 相依關係

```
writing-plans
    └─ 產出計畫 → 供 subagent-driven-development 讀取

subagent-driven-development
    ├─ Implementer 使用 → test-driven-development
    ├─ 審查使用 → requesting-code-review
    └─ 完成後使用 → finishing-a-development-branch

qa-orchestra
    └─ browser-validator 需要 → Chrome MCP（claude-in-chrome）
```

### 10.2 重要禁止事項

| 禁止 | 原因 |
|---|---|
| 跳過失敗測試直接寫實作 | 違反 TDD 鐵律，測試無驗證意義 |
| 跳過 Spec Review | 可能實作多餘功能或遺漏規格 |
| 跳過 Code Quality Review | 品質問題累積至後期更難修正 |
| 直接在 main/master 開發 | 沒有隔離保護，風險過高 |
| 使用 `--no-verify` 跳過 Git Hooks | 繞過安全門禁 |
| 截斷 QA 文件輸出 | QA 報告必須完整，不可省略 |

### 10.3 QA 發現 Bug 的處理流程

```
bug-reporter 產出 qa-output/bug-reports.md
    │
    ▼
回到階段三 SDD 執行
    │  建立新 Task（修正 Bug）
    │  Implementer → Spec Review → Quality Review
    ▼
重跑受影響的 QA 驗證
    │  @smart-test-selector 確認影響範圍
    │  @browser-validator 重新驗證
    ▼
QA 通過 → 繼續階段五收尾
```

### 10.4 跨 Session 記憶（episodic-memory）

若安裝了 `episodic-memory`，重要的開發決策會自動記錄，下次 Session 可直接查詢：

```
回顧上次 feature-name 的開發決策有哪些？
```

---

## 快速參考卡

```
啟動前
  claude plugin list  →  確認所有必要 Skills 已安裝

階段一  環境準備
  → using-git-worktrees      建立 feature branch
  → 建立 context/CONTEXT.md  提供給 QA 使用

階段二  計畫產製
  → 貼上 SA 藍圖
  → writing-plans            產出 docs/superpowers/plans/*.md

階段三  SDD 執行
  → subagent-driven-development
     每個 Task：Implementer（TDD）→ Spec Review → Quality Review

階段四  QA 測試
  → @orchestrator            全流程
  → @functional-reviewer     AC 合規審查
  → @browser-validator       瀏覽器實際驗證
  → @bug-reporter            產出 Bug 報告

階段五  收尾
  → finishing-a-development-branch
     Merge / PR / 清理 worktree
```

---

*文件產製日期：2026-05-07*
*適用工具：Claude Code + Superpowers Skills + qa-orchestra*
