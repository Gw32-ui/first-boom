# Git操作指南

## 当前状态
- Git仓库已初始化：C:\Users\17739\workflu\.git
- 当前分支：main
- 暂无提交记录

## 操作步骤

### 1. 创建初始备份（当前所有文件）
```bash
cd C:\Users\17739\workflu
git add -A
git commit -m "初始备份：项目基础结构"
```

### 2. 进行代码修改...

### 3. 如果需要回退
```bash
# 查看提交历史
git log --oneline

# 回退到某个commit
git reset --hard <commit-hash>

# 或者只恢复某个文件
git checkout HEAD -- path/to/file
```

### 4. 安全提交新修改
```bash
git add -A
git commit -m "添加功能：xxx"
```

## 注意事项
- quiz-platform子目录本身也是git仓库，建议忽略或作为submodule处理
- 大文件（如.db、.pdf）应添加到.gitignore