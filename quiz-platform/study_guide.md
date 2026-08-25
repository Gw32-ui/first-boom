# Workflu 程序学习指南（零基础）

## 第一部分：先补 Python 基础（1-2周）

### 必学知识点
| 概念 | 学习资源 |
|------|----------|
| 变量、字符串、列表、字典 | B站搜索"Python入门" |
| if/for/while 循环 | 同上 |
| 函数定义 def、参数、返回值 | 同上 |
| class 类、对象、继承 | 进阶部分 |
| import 模块导入 | 实战中理解 |

### 推荐学习路径
1. **菜鸟教程 Python** (runoob.com/python) — 有在线编辑器
2. **B站 Python 教程** — 搜索"Python零基础入门"
3. 实际动手：安装 Python + VS Code，运行 `print("hello")` 开始

---

## 第二部分：理解项目结构

```
quiz-platform/
├── app/                    # 主程序代码
│   ├── parser/             # [重点] 文本解析器
│   │   └── model_parser.py # 识别题干答案的核心
│   ├── grader/             # 判卷逻辑
│   ├── storage/            # 数据库操作
│   ├── vision/             # 图片处理
│   └── web.py              # Web服务入口
├── config/config.yaml      # 配置文件
├── data/questions.db       # 题库数据库（SQLite）
└── output/images/          # 图片缓存目录
```

### 学习顺序

#### Step 1：先看最核心的文件（不要求懂全部）
1. **`app/parser/model_parser.py`** — 800行，理解如何把文本切成题目
2. **`app/models/question.py`** — 37行，理解数据长什么样
3. **`app/storage/db_manager.py`** — 140行，理解数据存储

#### Step 2：看数据流（从输入到输出）
```
上传文件 → extract_bytes_text() → parse_text() → Question对象 → 存数据库
```

#### Step 3：看具体函数
- `_split_blocks()` — 怎么切题
- `_parse_block()` — 怎么提取题干答案
- `check_answer()` — 怎么判对错

---

## 第三部分：实战学习方法

### 方法1：打印调试
在关键位置加 print，看程序怎么走：
```python
# model_parser.py 第350行附近
print(f"检测到答案行: {line}")
```
然后运行程序，观察输出。

### 方法2：单步追踪
用 VS Code 的 Debug 功能，打断点，一行行执行看变量变化。

### 方法3：读数据不看代码
打开 `data/questions.db`，用 DB Browser for SQLite 查看实际存储的题目格式。

---

## 第四部分：快速上手任务

| 任务 | 难度 | 涉及文件 |
|------|------|----------|
| 修改一道题目的显示样式 | ⭐ | `app/web.py` |
| 添加一个新的题型判断规则 | ⭐⭐ | `app/parser/model_parser.py` |
| 修改答案判对的逻辑 | ⭐⭐ | `app/grader/answer_checker.py` |
| 增加一个文件预处理步骤 | ⭐⭐⭐ | `app/parser/file_loader.py` |

---

## 第五部分：遇到问题怎么办

1. **复制错误信息** → 粘贴到 ChatGPT/Claude 问
2. **搜索关键词** → `site:github.com workflu "错误提示"`
3. **读注释** → 项目里已有中文注释说明逻辑
4. **问 AI** → 把代码段落发给 AI，让它解释

---

## 附：本项目关键术语对照表

| 英文术语 | 中文意思 | 代码位置 |
|----------|----------|----------|
| Question | 一道题目 | `models/question.py` |
| parse | 解析 | `parser/model_parser.py` |
| grade | 判卷 | `grader/grader.py` |
| storage | 存储 | `storage/db_manager.py` |
| webhook | 回调通知 | `web.py` |
| middleware | 中间件 | `web.py` |
