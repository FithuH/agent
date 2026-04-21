"""
utils/ast_extractor.py
提取 Python 代码的 AST 骨架，作为极致轻量级的上下文记忆。
"""
import ast

def _extract_skeleton(self, content: str) -> str:
        """
        AST 语法树提取：终极版 (需 Python 3.9+)
        完美保留函数参数类型 (Args) 与 返回值类型 (Return Types)
        """
        import ast
        try:
            tree = ast.parse(content)
        except Exception:
            return "语法错误或非 Python 文件"
            
        lines = []
        for node in tree.body:
            # 1. 提取全局常量... (保留你之前的代码)
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        lines.append(f"{target.id} = ...")
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id.isupper():
                lines.append(f"{node.target.id} = ...")
                    
            # 2. 提取类
            elif isinstance(node, ast.ClassDef):
                lines.append(f"class {node.name}:")
                has_content = False
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef):
                        # 【核心强化】：利用 ast.unparse 精确还原带类型的签名
                        args_str = ast.unparse(sub.args)
                        ret_str = f" -> {ast.unparse(sub.returns)}" if sub.returns else ""
                        lines.append(f"    def {sub.name}({args_str}){ret_str}: ...")
                        has_content = True
                    # (省略其他的 Assign 提取逻辑...)
                if not has_content:
                    lines.append("    pass")
                    
            # 3. 提取全局函数
            elif isinstance(node, ast.FunctionDef):
                # 【核心强化】：利用 ast.unparse 精确还原带类型的签名
                args_str = ast.unparse(node.args)
                ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                lines.append(f"def {node.name}({args_str}){ret_str}: ...")
                
        return "\n".join(lines) if lines else "无公开接口"