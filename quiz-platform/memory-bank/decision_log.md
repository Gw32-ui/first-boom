# 关键决策记录（Decision Log）

## D001：OCR 使用 GLM-4.6V-Flash 云端视觉而非本地 OCR
- 理由：本地 Tesseract/Pix2Text 对数学公式识别差；GLM Flash 免费、免 GPU、已配置 API Key
- 替代方案：Ollama qwen3-vl（已配置但依赖本机 Ollama 运行）；PaddleOCR-LaTeX（未集成）
- 风险：依赖网络与云端 API；黑图/大图需预处理（image_utils.py）

## D002：保留正则解析器作为第一档
- 理由：DOCX/带文本层 PDF 秒级解析、零成本；视觉 OCR 作为扫描件兜底
- 风险：题型检测/多题合并依赖正则与文本布局，误判率高
- 后续计划：解析结果可回退到视觉清洗（mcp ocr_clean）；题型规则收敛到单一模块

## D003：修复范围合并对话中发现的问题（2026-08-18）
- 除原 23 项清单外，合并对话中确认的逻辑错误：
  - faiss 模块级硬依赖导致服务无法启动
  - /api/build-index 调用不存在的 list_all_questions
  - 启动打印 emoji 在 GBK 重定向下崩溃
  - 图片按题目序号硬绑（位置错位）
  - docx 同名媒体文件互相覆盖/引用错图
  - 知识点行被丢弃、不写入 topic
  - 多选数字答案被清洗丢失；填空顺序/数量强约束误判
  - LLM 判卷 “不正确” 含 “正确” 子串误判
- 决策：测试先行（重建 tests/），一次只改一个模块，模块间规则共享

## D004：判断题 A/B 不再强映射（2026-08-18）
- 问题：A→对、B→错 在选项顺序反转时语义颠倒
- 决策：清洗与判卷都去掉字母强映射；判卷时若有选项文本，按选项内容映射；无法映射则 pending

## D005：计算题判卷改为表达式求值（2026-08-18）
- 决策：安全 AST 求值（分数/√/π/乘方），失败退回数字提取；容差 rel≤5e-4 且 abs≤1e-6
- 保留限制：整段含题干文字的答案（如 f(0)=1）仍可能数字个数不匹配，列入待办

## D006：faiss 改为懒加载（2026-08-18）
- 问题：模块级 import faiss 导致 DLL 异常时整个服务无法启动
- 决策：web.py 内 _get_embedding_service() 延迟导入；向量接口单独返回可读错误

## D007：docx 图片分类切到智谱 GLM-4.6V-Flash（2026-08-20）
- 问题：config.yaml 的 vision 段仍指向本地 Ollama（127.0.0.1:11434 / qwen3-vl:2b），
  docx 上传时 image_classify.py 自动 POST 到该地址，拉起 llama.exe 占显存
- 决策：vision / llm 配置默认智谱 OpenAI 兼容端点，api_key 从 .env 的 ZHIPU_API_KEY 回退；
  移除 Ollama 默认配置；classify_image_vision 增加 429 重试与严格 JSON 提示
- 配套：新增 app/llm/zhipu_client.py 统一 chat 调用（判卷 / 图片分类 / 变式 / AI 整理共用）；
  导入链路新增 HTML 实体反转义（&gt; &lt; &amp; 等）；题库页新增批量删除；
  新增变式出题与 AI 文本整理接口
