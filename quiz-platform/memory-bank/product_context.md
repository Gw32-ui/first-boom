# 产品上下文（Product Context）

## 目标用户
- 高校教师：导入课程材料、维护题库、组卷、布置练习
- 学生：专项训练、自由组卷、答题、查看判卷结果

## 核心流程
上传文件（PDF/DOCX/TXT）→ OCR/解析 → 入库 → 选题出卷 → 答题判卷 → 历史记录

## 非目标（当前明确不做）
- 用户账号系统 / 权限体系（仅本机 127.0.0.1 访问）
- 错题本 / 学习报告
- 题库/试卷导出（仅历史记录支持 JSON/CSV）
- 云部署 / 内网穿透

## 当前约束
- 纯本地运行，数据落盘 SQLite（data/questions.db）
- 题型枚举固定：single_choice / multiple_choice / blank / judge / essay / calc / thinking
- Question 模型字段冻结，只增不改
