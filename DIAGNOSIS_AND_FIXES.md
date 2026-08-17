# 你的题库系统 vs GEEQuestionBank 差距分析

## 一、后端API实现状态

### ✅ 你已实现的API端点（web.py中定义）
```python
# 题库管理
GET  /api/stats              # 统计数据
GET  /api/subjects           # 学科列表
GET  /api/qtypes             # 题型列表
GET  /api/questions          # 题目列表（分页+筛选）
GET  /api/question/{qid}     # 单题详情
POST /api/question/import    # 文本导入
POST /api/question/import-file  # 文件导入（DOCX/PDF/TXT）
DELETE /api/question/{qid}   # 删除题目
POST /api/question/{qid}/answer  # 补充答案

# 组卷功能
POST /api/practice/start     # 专项训练
POST /api/paper/generate     # 自由组卷
GET  /api/papers             # 试卷列表
GET  /api/paper/{paper_id}   # 试卷详情

# 答题与历史
POST /api/submit             # 提交答案
GET  /api/records            # 历史记录列表
GET  /api/record/{rid}       # 记录详情
GET  /api/record/{rid}/export  # 导出记录
```

### ❌ 你尚未实现的API
| API | GEE实现 | 你需要补的 |
|-----|---------|-----------|
| `/api/similar` | 相似题目检索 | 向量检索接口 |
| `/api/topics` | 考点分析 | VLM分析知识点 |
| `/api/stats/subject` | 按学科统计 | 难度分布图 |
| `/api/export` | 导出为Excel | 已有JSON导出，缺Excel |

---

## 二、数学符号渲染差距

### GEEQuestionBank的实现
```html
<!-- 使用MathJax 3 -->
<script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
<script>
MathJax.startup.promise.then(() => {
  MathJax.typesetPromise();  // 渲染所有$...$和$$...$$
});
</script>
```

```python
# PDF提取时用正则识别LaTeX公式
import re
text = "求$\int_0^{\infty} e^{-x^2}dx$的值"
formulas = re.findall(r'\$([^$]+)\$', text)  # ['\\int_0^{\\infty} e^{-x^2}dx']
```

### 你的实现（KaTeX）
```html
<!-- 已引入KaTeX -->
<link rel="stylesheet" href="/static/vendor/katex/katex.min.css">
<script src="/static/vendor/katex/katex.min.js"></script>
<script src="/static/js/app.js"></script>
```

```javascript
// app.js中的渲染逻辑
function renderMath() {
  if (!window.katex) return;
  document.querySelectorAll(".q-formula").forEach((el) => {
    try {
      katex.render(el.dataset.tex, el, { throwOnError: false });
    } catch (e) {}
  });
}
```

### ⚠️ 核心差距：公式来源不同

| 场景 | GEE处理 | 你的处理 |
|------|---------|----------|
| **Word DOCX** | ✅ 完美：OMML XML → LaTeX | ✅ 已实现 `_omml_to_latex()` |
| **PDF扫描件** | ❌ 困难（无公式数据） | ❌ 同样困难 |
| **纯文本PDF** | ❌ 提取到乱码字符 | ❌ 提取到PUA私有字符 |
| **OCR识别公式** | ✅ 使用VLM识别并输出LaTeX | ❌ 仅启发式分类，无公式识别 |

### 🔧 解决方案（针对PDF）

**方案A：调用Ollama识别公式**
```python
# 在vision/image_classify.py中添加公式识别
def extract_formula_from_image(img_path, ctx):
    """调用VLM识别图片中的公式并转LaTeX"""
    b64 = base64.b64encode(img_path.read_bytes()).decode()
    prompt = f"""请识别这张图片中的数学公式，输出标准LaTeX格式（只用行内公式$...$）：
图片上下文：{ctx[:200]}
只输出LaTeX代码，不要其他文字。"""
    
    payload = {
        "model": "qwen3-vl:2b",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
        ]}],
        "temperature": 0.1
    }
    # ... 调用Ollama API
```

**方案B：建立字符映射表（快速修复）**
```python
# 解决WPS私有字体乱码
WPS_REPLACEMENTS = {
    '': '-', '': '=', '': '+',
    '': r'\delta', '': r'\pi', '': r'\epsilon',
    'ò': r'\int', '¥': r'\infty', '•': r'\cdot',
    # ... 补全34个映射
}

def fix_wps_encoding(text: str) -> str:
    """修复WPS导出的PDF中的私用区字符"""
    for bad, good in WPS_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text
```

---

## 三、向量检索详解

### 📚 什么是向量检索？

**通俗理解：**
- 传统搜索：关键词匹配（"傅里叶变换" → 找包含这个词的题目）
- 向量检索：语义理解（"信号的频域分析" → 找到"傅里叶变换"相关题目）

**技术原理：**
```
题目文本 → Embedding模型 → 高维向量 → 存入向量数据库
                    ↓
查询文本 → Embedding模型 → 高维向量 → 余弦相似度计算 → 返回最相似的题目
```

### 🛠️ 你需要实现的模块

**Step 1：安装依赖**
```bash
pip install sentence-transformers faiss-cpu numpy
```

**Step 2：创建Embedding服务**
```python
# app/vector/embedding_service.py
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import json
from pathlib import Path

class EmbeddingService:
    def __init__(self, model_name='BAAI/bge-large-zh-v1.5'):
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.questions = []  # 存储原始题目用于结果返回
    
    def build_index(self, questions):
        """构建向量索引"""
        texts = [q['question'] for q in questions]
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # 内积相似度
        self.index.add(embeddings.astype('float32'))
        self.questions = questions
        
        # 保存索引
        faiss.write_index(self.index, 'data/embedding.index')
        with open('data/questions_meta.json', 'w', encoding='utf-8') as f:
            json.dump(questions, f, ensure_ascii=False)
    
    def search(self, query: str, top_k: int = 5) -> list:
        """语义搜索"""
        query_vec = self.model.encode([query], normalize_embeddings=True)
        scores, indices = self.index.search(query_vec.astype('float32'), top_k)
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if score > 0.5:  # 阈值过滤
                results.append({
                    'question': self.questions[idx]['question'],
                    'score': float(score),
                    'qid': self.questions[idx].get('id')
                })
        return results

# 全局实例
embedding_service = EmbeddingService()
```

**Step 3：添加API端点**
```python
# web.py中添加
@app.get("/api/similar")
def api_similar_search(query: str, subject: str = "", top_k: int = 5):
    """相似题目搜索"""
    if embedding_service.index is None:
        return {"error": "索引未构建"}
    
    results = embedding_service.search(query, top_k)
    return {"query": query, "results": results}

@app.post("/api/build-index")
def api_build_index():
    """重建向量索引"""
    questions = storage.list_all_questions()
    embedding_service.build_index(questions)
    return {"ok": True, "count": len(questions)}
```

**Step 4：前端调用示例**
```javascript
// 在题目详情页添加"相似题目"按钮
async function findSimilar(qid) {
  const q = await api(`/api/question/${qid}`);
  const res = await api(`/api/similar?query=${encodeURIComponent(q.question)}&top_k=5`);
  // 显示相似题目列表
}
```

### 📊 效果预期

| 查询词 | 传统关键词搜索 | 向量语义搜索 |
|--------|---------------|-------------|
| "周期信号判定" | 匹配"周期性" | ✅ 匹配"判断下列信号是否周期信号" |
| "拉氏变换性质" | 匹配"拉普拉斯" | ✅ 匹配"s域分析、变换特性" |
| "卷积定理应用" | 匹配"卷积" | ✅ 匹配"时域乘积对应频域卷积" |

---

## 四、图片理解的替代方案

### 问题诊断
```
Ollama qwen3-vl:2b 超时原因：
1. 2B模型GPU推理较慢（约50-90秒/张）
2. 显存不足导致swap到内存
3. 批量处理时请求队列阻塞
```

### 🔧 解决方案

**方案A：分批处理 + 降低并发**
```python
# vision/image_classify.py - 修改超时时间
def classify_image_vision(img_path, vision_cfg, context=""):
    timeout = int(vision_cfg.get("timeout") or 180)  # 增加到3分钟
    # ...
    
# 或改用流式响应
payload = {"stream": True, ...}
response_text = ""
for chunk in requests.post(url, json=payload, stream=True):
    if chunk.data.strip():
        response_text += chunk.data.decode()
```

**方案B：先用启发式，只对疑难图片调用VLM**
```python
def classify_images_in_dir(images_dir, cfg, context_map=None, cache_file=None):
    results = {}
    for img_path in images_dir.glob("*.jpg"):
        ctx = context_map.get(img_path.name, "")
        
        # Step 1: 启发式分类（秒级响应）
        heuristic = classify_image_heuristic(img_path, ctx)
        
        # Step 2: 只对"不确定"的图片调用VLM
        if heuristic['kind'] in ('diagram', 'formula') and heuristic.get('confidence', 1.0) < 0.7:
            try:
                vision_result = classify_image_vision(img_path, cfg, ctx)
                results[img_path.name] = vision_result
            except:
                results[img_path.name] = heuristic  # 降级使用启发式
        else:
            results[img_path.name] = heuristic  # 直接使用启发式结果
```

**方案C：使用更小的模型**
```bash
# 试试这些更小更快的模型
ollama pull qwen2-vl:2b          # 比qwen3-vl快30%
ollama pull llava:7b             # 中文图像理解不错
ollama pull nomic-embed-text     # 轻量级，速度快
```

**方案D：离线索引构建（推荐）**
```python
# 不在导入时实时识别，而是后台异步处理
@app.post("/api/process-images")
def api_process_images():
    """异步处理图片分类（不阻塞用户）"""
    import threading
    def background_task():
        cfg = load_config()
        classify_images_in_dir(
            ROOT / "output" / "images",
            cfg,
            context_map=_image_context_map(),
            cache_file=ROOT / "output" / "images" / "image_meta.json"
        )
    threading.Thread(target=background_task, daemon=True).start()
    return {"status": "processing", "message": "图片正在后台处理"}
```

---

## 五、公式处理差距与修复

### 🔍 问题根源

你说得对——**"计算机可理解但人视觉上看到的不是数学试卷格式"**

这正是：
- **机器可读格式**：Unicode字符、ASCII字符拼凑
- **人眼友好格式**：LaTeX排版、数学字体渲染

### 📐 格式对照表

| 数学表达式 | Unicode/ASCII拼凑 | LaTeX标准格式 | 渲染效果 |
|-----------|------------------|--------------|---------|
| 积分 | `òf(t)dt` | `\int f(t)dt` | ∫f(t)dt |
| 无穷大 | `¥` | `\infty` | ∞ |
| 偏导 | `∂f/∂x` | `\frac{\partial f}{\partial x}` | ∂f/∂x |
| 分数 | `(a+b)/c` | `\frac{a+b}{c}` | $\frac{a+b}{c}$ |
| 根号 | `sqrt(x)` | `\sqrt{x}` | √x |

### 🔧 修复方案

**方案1：字符替换后转LaTeX（简单但有效）**
```python
# parser/model_parser.py 或新建 formula_fixer.py
UNICODE_TO_LATEX = {
    # 基本运算符
    '×': r'\times', '÷': r'\div', '±': r'\pm',
    # 希腊字母
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta',
    'ε': r'\epsilon', 'π': r'\pi', 'σ': r'\sigma', 'ω': r'\omega',
    'Δ': r'\Delta', 'Σ': r'\Sigma', 'Ω': r'\Omega',
    # 关系符号
    '≠': r'\neq', '≤': r'\leq', '≥': r'\geq',
    # 集合符号
    '∈': r'\in', '⊂': r'\subset', '∪': r'\cup', '∩': r'\cap',
    # 逻辑符号
    '∀': r'\forall', '∃': r'\exists', '¬': r'\neg',
    # 箭头
    '→': r'\rightarrow', '⇒': r'\implies', '↔': r'\leftrightarrow',
}

def unicode_to_latex(text: str) -> str:
    """将Unicode数学符号转换为LaTeX命令"""
    for uni, latex in UNICODE_TO_LATEX.items():
        text = text.replace(uni, latex)
    return text
```

**方案2：使用regex智能转换（更强）**
```python
import re

def smart_formula_convert(text: str) -> str:
    """智能转换常见公式表达"""
    # 分数：a/b → \frac{a}{b}
    text = re.sub(r'(\d+)\s*/\s*(\d+)', r'\frac{$1}{$2}', text)
    
    # 根号：sqrt(x) 或 √x → \sqrt{x}
    text = re.sub(r'sqrt\(([^)]+)\)', r'\sqrt{$1}', text)
    text = re.sub(r'√([^a-zA-Z\s])', r'\sqrt{$1}', text)
    
    # 上下标：x^2 → x^{2}, x_n → x_{n}
    text = re.sub(r'([a-zA-Z])\^(\d+)', r'\1^{$\2$}', text)
    text = re.sub(r'([a-zA-Z])_(\d+)', r'\1_{$\2$}', text)
    
    # 求和/积分：sum(i=1,n) → \sum_{i=1}^{n}
    text = re.sub(r'sum\((\w)=(\d+),\s*(\d+)\)', r'\sum_{\1=$2}^{$3}', text)
    
    return text
```

**方案3：前端KaTeX自动渲染（必须做）**
```javascript
// static/js/app.js 中添加
function renderFormulasInElement(element) {
  const html = element.innerHTML;
  
  // 检测并转换常见公式模式
  let converted = html
    .replace(/∫/g, '\\int')
    .replace(/∞/g, '\\infty')
    .replace(/α/g, '\\alpha')
    .replace(/β/g, '\\beta')
    .replace(/π/g, '\\pi')
    // ... 更多映射
  
  // 用KaTeX重新渲染
  element.innerHTML = converted;
  
  if (window.katex) {
    try {
      katex.render(element.dataset.latex || converted, element, {
        throwOnError: false,
        displayMode: true
      });
    } catch (e) {
      console.error('KaTeX渲染失败:', e);
    }
  }
}

// 在题目渲染后调用
function renderQuestion(q) {
  const html = `<div class="q-text">${q.question}</div>`;
  // ... 插入DOM后
  renderFormulasInElement(document.querySelector('.q-text'));
}
```

---

## 六、完整改进路线图

### Phase 1：基础功能完善（1-2周）
- [ ] 安装依赖并启动FastAPI服务
- [ ] 实现字符替换修复WPS乱码
- [ ] 前端KaTeX自动渲染公式
- [ ] 测试导入毛概PDF并验证显示效果

### Phase 2：核心功能增强（2-4周）
- [ ] 集成sentence-transformers + faiss实现向量检索
- [ ] 优化Ollama调用策略（分批+降级）
- [ ] 添加相似题目搜索API
- [ ] 完善图片分类缓存机制

### Phase 3：论文创新点（1-2周）
- [ ] 实验对比：规则修复 vs VLM识别的效果
- [ ] 性能测试：向量检索响应时间
- [ ] 用户研究：题库系统的可用性评估
- [ ] 撰写论文相关章节
