#!/usr/bin/env python3
"""添加健康检查端点到 main.py"""

import sys

# 读取文件
with open("app/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# 检查是否已有 /health 端点
if "def health_check" in content or '@app.get("/health")' in content:
    print("健康检查端点已存在")
    sys.exit(0)

# 在 home() 函数后添加 health_check
health_endpoint = '''

@app.get("/health")
def health_check():
    """健康检查端点，用于测试脚本验证后端状态"""
    return {
        "status": "ok",
        "service": "DriftSystem Backend",
        "version": "2.0",
    }
'''

# 找到 home() 函数的结束位置
lines = content.split('\n')
new_lines = []
in_home_function = False
brace_count = 0
insert_index = -1

for i, line in enumerate(lines):
    new_lines.append(line)
    
    if 'def home():' in line:
        in_home_function = True
        brace_count = 0
        
    if in_home_function:
        # 计算缩进来判断函数结束
        if line.strip() and not line.strip().startswith('#'):
            if line.startswith('    }') or (line.startswith('@') and i > 0):
                insert_index = i
                in_home_function = False

if insert_index > 0:
    new_lines.insert(insert_index, health_endpoint)
    
    with open("app/main.py", "w", encoding="utf-8") as f:
        f.write('\n'.join(new_lines))
    
    print("✓ 已添加健康检查端点")
else:
    print("✗ 未找到合适的插入位置")
    sys.exit(1)
