---
name: pdf-question-cleaner
description: 'Use when the user needs to clean a PDF question bank containing mixed handwritten text, images, and printed text — converting exam/review PDFs into structured question format (题目｜答案) for import into a quiz system. Triggers on requests like "清洗PDF题库", "把PDF题转成题库格式", "处理扫描版复习题".'
---

# PDF题库清洗工具

## 触发条件
Use when the user wants to clean a PDF question bank containing mixed handwritten text, images, and printed text — especially converting exam/复习题 PDFs into structured question format for import into a quiz system.

## 输入参数
`$ARGUMENTS` 为 PDF 文件路径，例如：`E:\桌面\总复习题.pdf`
可选参数：`--output 输出目录`（默认桌面/test/题库）

## 执行步骤

### Step 1：检查 PDF 基本信息
运行命令获取文件信息：
```powershell
Get-Item "$ARGUMENTS" | Select-Object FullName, Length, LastWriteTime
```
用 Python 获取页数和首行文字预览：
```python
import fitz, sys
doc = fitz.open(sys.argv[1])
print(f"页数: {len(doc)}")
print("前500字:", doc[0].get_text()[:500])
```
判断：能否复制文字 → 纯文本PDF；不能 → 扫描件需OCR。

### Step 2：去除手写痕迹（如需要）
如果PDF包含手写笔迹（答案、勾选等干扰项）：
- 引导用户使用 https://erasewriting.com 上传PDF在线擦除手写内容
- 或指导使用 Adobe Acrobat Pro 手动擦除
- 处理后保存到临时路径

### Step 3：OCR文字识别（仅扫描版PDF）
如果Step 1确认是扫描图片型PDF：
- 推荐工具：**Umi-OCR**（开源免费，支持中文，离线可用）
- 下载地址：https://github.com/hiroi-sora/Umi-OCR/releases
- 操作步骤：打开软件 → 导入PDF → 语言选"中文简体" → 导出TXT

### Step 4：格式清洗与拆分
将OCR结果按以下规则拆分为题库格式：

```python
import re

def parse_questions(text):
    lines = text.split('\n')
    questions = []
    current = ''
    for line in lines:
        # 遇到数字编号开头的新题 → 保存旧题，开新题
        if re.match(r'^\d+[\.\)）]', line.strip()):
            if current.strip():
                questions.append(current.strip())
            current = line
        else:
            current += ' ' + line
    if current.strip():
        questions.append(current.strip())
    
    result = []
    for q in questions:
        # 删除答案行（包含"答案"关键字的行）
        q_clean = re.sub(r'答案[：:].*', '', q)
        # 分离选项
        q_clean = re.sub(r'(A\.|B\.|C\.|D\.)', r'\n\1', q_clean)
        q_clean = q_clean.strip()
        if q_clean:
            result.append(q_clean)
    return result
```

### Step 5：生成题库文件
输出格式为 `题目｜答案` 一行一道题，保存至输出目录：
```
题目内容｜答案
lim(x→0) sin(x)/x 的值为？|B
sin²θ + cos²θ = ______|1
```

### Step 6：报告结果
输出统计信息：
- 处理总页数
- 识别题目数量
- 题型分布（选择/填空/判断/简答等）
- 输出文件路径

## 输出文件
保存到 `$ARGUMENTS` 同级目录下的 `test/题库/` 子目录中，命名为 `题库_清洗结果.txt`

## 停止条件
- 成功：输出文件已生成，并展示统计摘要
- 失败：如PDF无法读取或OCR无文字，报告错误原因并停止，不建议用户手动重试失败路径
