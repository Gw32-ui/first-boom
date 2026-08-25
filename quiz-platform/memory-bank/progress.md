# 开发进度追踪（Progress）

## 2026-08-18 建立上下文
- [x] Memory Bank 四件套
- [x] 核对 Bug 清单：P0-1（JUDGE_ 未定义）为假 Bug，已剔除
- [x] 确认 tests/ 缺失，需先重建测试

## 待办（按模块顺序）
- [x] tests/ 重建（25 个用例，pytest 全绿）
- [x] model_parser.py：essay/calc explicit、BLANK_MARK 排除 LaTeX、判断题题干模式、TYPE_KEYWORDS 顺序（多选/多项/不定项优先）、计算/简答关键词、多选数字答案、知识点→topic、判断字母不强制映射
- [x] answer_checker.py：判断 A/B 按选项语义映射、计算题分数/√/π 安全求值、Y/N、简答有答案归 pending
- [x] web.py：faiss 懒加载、build-index 修复、启动 stdout 编码、上传 50MB 限制、qtype 校验、扫描 PDF GLM OCR 兜底、图片只存文件名、topic 入库
- [x] 存储层：WAL/busy_timeout、question 列索引、list_all_questions
- [ ] 批量事务导入（add_questions_batch，P2）
- [ ] 前端判断题取值一致、规则共享收敛（P2）
- [ ] docx 同名媒体文件冲突修复（P2）
- [ ] LLM 判卷否定词（已修）→ 待前端接入回归

## 2026-08-18 完成 P0/P1 修复（25 tests 全绿）
- 解析层 12 用例、判卷层 10 用例、存储/导入链路 3 用例
- 变更文件：model_parser.py、answer_checker.py、grader.py、llm_client.py、web.py、db_manager.py、question_repo.py、storage/__init__.py

## 2026-08-18 下午：主程序瘦身 + 老库迁移
- [x] 删除启动调试打印（公式修复测试）
- [x] 删除 templates 模板加载链（load_templates/get_available_templates/generate_from_template + templates/default.json，前端用硬编码预设）
- [x] 删除 documents 旧版管理函数（add_document/get_document/find_document_by_filename/clear_questions_by_doc/delete_document/delete_subject/get_topics，无 API 调用）
- [x] 老库合并题迁移：5 条【x-y】合并行 → 拆成 16 条独立题（17 条重复跳过），备份 data/questions.db.bak_20260818_142711
- 测试：28 passed

## 2026-08-18 晚：图题匹配 + MD5 去重 + 残缺标记（接力 Cline 完成）
- [x] ① 图题匹配：pyproject 加 pymupdf；file_loader.py 新增 extract_pdf_rich（位图+矢量图坐标级锚点【图:文件名】，文本块与图片按坐标排序合并）；web.py PDF 分支接入
- [x] ② MD5 去重：db_manager 增加 content_hash 列 + idx_questions_content_hash；question_repo 新增 content_hash/add_question_dedup/find_question_by_hash；web.py _run_import 接入（inserted/merged/pending_review 统计，source_file 透传，paper_files 记录来源）
- [x] ③ 残缺标记：model_parser 新增 mark_pending_review（<Formula>/<ImgRef> 占位符 → pending_review）；web.py 新增 /api/admin/pending-questions、/api/admin/pending/{qid}/clear、/api/admin/pending/{qid}/resolve；前端新增“复核”页（补全并确认对齐/直接确认对齐）
- [x] 真实库迁移：content_hash + pending_review 列已补（备份 data/questions.db.bak_20260818_222148）；2087 条存量题目回填指纹；清理 1 条存量重复题（id 1429，与 1428 完全相同）
- 测试：32 passed（新增指纹归一化/去重合并/残缺复核 3 个用例）

## 已知风险
- [大幅缓解] 图片按题目序号绑定错位：PDF 已改坐标级锚点（extract_pdf_rich）；docx 走段落内嵌
- 填空顺序无关比较对“有序填空”会误判正确

## 2026-08-21 图片链路完整修复（OCR 不丢图 + 归属回填 + 视觉分类 + 管理界面）
- [x] 修复致命断点：公式型 PDF 走 OCR 兜底时图片全部丢失 → extract_pdf_rich_meta 返回图片事件+题号标记，
      map_pdf_images_to_questions 按坐标把图归属到题号，OCR 文本解析后按题号回填【图:】锚点；
      题号对不上/缺失时顺序兜底绑定并标 pending_review（不丢图、不猜）
- [x] 修复真实 bug：PyMuPDF 1.28 get_image_info() 默认不返回 xref → PDF 位图以前一直提取不到，已改 xrefs=True
- [x] _run_import 图片索引绑定去重错位修复：图片随 Question 携带；images 字段与题干锚点统一
- [x] content_hash 忽略【图:】锚点：同题带图/不带图跨文件仍可指纹去重
- [x] add_question_dedup 合并分支：新内容带图升级 images 字段；旧题有锚点而新内容没有时不覆盖
- [x] 视觉分类接入 PDF 分支 + classify_images_in_dir 支持 only（不再扫全目录）；
      公式图（LaTeX 校验通过）→ 嵌入题干，装饰图 → 移除，坏 LaTeX → 保留原图
- [x] docx：媒体名加 doc_ 前缀防跨文档同名冲突；EMF/WMF/TIFF 转 PNG，失败保留原文件并记录
- [x] 新 API：PUT /api/question/{id}/images、POST /api/images/upload、GET /api/admin/image-stats
- [x] 前端：richText 锚点文件名不再被 esc 后二次编码；列表截断改为先截原文再渲染；
      images 字段与题干锚点去重显示；复核页图片上传/删除/插题干；导入结果展示图片统计
- [x] 诊断脚本 scripts/diagnose_images.py（有图题数/锚点/缺失文件/孤儿图/分类失败统计）
- [x] config.yaml 移除明文视觉 API Key（改走 .env）
- 测试：82 passed（新增坐标映射、OCR 回填、端到端真实 PDF、图片管理 API、诊断统计等）
- 待办：用真实试卷（周周测5.pdf / 模拟题1.pdf）人工抽查锚点归属与公式图 LaTeX 效果
