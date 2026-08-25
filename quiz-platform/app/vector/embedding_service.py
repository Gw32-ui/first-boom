"""向量检索服务 - 基于BGE-M3 + FAISS的相似题目搜索"""
from __future__ import annotations
import json
import faiss
import numpy as np
from pathlib import Path
from typing import Optional

try:
    from sentence_transformers import SentenceTransformer
    HAS_ST = True
except ImportError:
    HAS_ST = False
    print("警告: sentence-transformers未安装，向量检索功能不可用")


class EmbeddingService:
    """文本向量化工具类"""
    
    def __init__(self, model_name: str = 'BAAI/bge-large-zh-v1.5'):
        self.model_name = model_name
        self.model = None
        self.index = None
        self.questions = []  # [{id, question, subject, ...}]
        self.embeddings = None
        self.data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        
    def init_model(self):
        """初始化Embedding模型（首次调用时加载）"""
        if self.model is None and HAS_ST:
            print(f"正在加载Embedding模型: {self.model_name}...")
            self.model = SentenceTransformer(self.model_name)
            print("模型加载完成!")
            
    def build_index(self, questions: list[dict]):
        """构建向量索引
        
        Args:
            questions: 题目列表，每项包含id, question, subject等字段
        """
        if not questions:
            return
            
        self.init_model()
        if not self.model:
            return
            
        # 提取所有题目文本
        texts = [q.get('question', '') for q in questions]
        
        # 生成向量
        print(f"正在编码 {len(texts)} 道题目...")
        embeddings = self.model.encode(
            texts, 
            normalize_embeddings=True,  # L2归一化，用于余弦相似度
            show_progress_bar=True
        )
        
        # 构建FAISS索引
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # 内积 = 余弦相似度
        self.index.add(embeddings.astype('float32'))
        
        # 保存元数据
        self.questions = questions
        
        # 持久化
        self._save_index()
        print(f"索引构建完成! 维度: {dimension}, 题目数: {len(questions)}")
        
    def search(self, query: str, top_k: int = 5, threshold: float = 0.6) -> list[dict]:
        """语义搜索相似题目
        
        Args:
            query: 查询文本
            top_k: 返回数量
            threshold: 相似度阈值
            
        Returns:
            [{"qid": ..., "question": ..., "score": ..., "subject": ...}]
        """
        if self.index is None:
            self._load_index()
            
        if self.index is None:
            return []
            
        self.init_model()
        if not self.model:
            return []
            
        # 编码查询
        query_vec = self.model.encode([query], normalize_embeddings=True)
        
        # 搜索
        scores, indices = self.index.search(
            query_vec.astype('float32'), 
            min(top_k, len(self.questions))
        )
        
        # 过滤并格式化结果
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if score >= threshold and idx < len(self.questions):
                q = self.questions[idx]
                results.append({
                    'qid': q.get('id'),
                    'question': q.get('question', ''),
                    'subject': q.get('subject', ''),
                    'score': float(score),
                })
                
        return results
    
    def _save_index(self):
        """保存索引到磁盘"""
        index_path = self.data_dir / "embedding.index"
        meta_path = self.data_dir / "questions_meta.json"
        
        faiss.write_index(self.index, str(index_path))
        
        # 只保存必要字段
        meta = []
        for q in self.questions:
            meta.append({
                'id': q.get('id'),
                'question': q.get('question', '')[:200],  # 截断避免太大
                'subject': q.get('subject', ''),
                'qtype': q.get('qtype', ''),
            })
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
            
        print(f"索引已保存到: {index_path}")
        
    def _load_index(self):
        """从磁盘加载索引"""
        index_path = self.data_dir / "embedding.index"
        meta_path = self.data_dir / "questions_meta.json"
        
        if not index_path.exists() or not meta_path.exists():
            return
            
        try:
            self.index = faiss.read_index(str(index_path))
            with open(meta_path, 'r', encoding='utf-8') as f:
                self.questions = json.load(f)
            print(f"索引已加载: {self.index.ntotal} 条记录")
        except Exception as e:
            print(f"加载索引失败: {e}")
            self.index = None


# 全局单例
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """获取全局Embedding服务实例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
