"""
HBM3E vs HBM4 世代对比柱状图
- I/O 位宽、pin 速率、单栈带宽、单栈容量、能效
数据源：Samsung Newsroom / SK hynix / Micron IR / JEDEC JESD270-4
生成：300 DPI PNG
"""
import matplotlib.pyplot as plt
import numpy as np

# 中文字体（若系统无中文字体，回退英文标签）
try:
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass

# 数据表（英文以避免字体问题）
metrics = [
    'I/O Width\n(bit)',
    'Pin Speed\n(Gb/s, max)',
    'Bandwidth\n(TB/s per stack)',
    'Capacity 12H\n(GB/stack)',
    'Capacity 16H\n(GB/stack)'
]
hbm3e = [1024, 9.6, 1.2, 24, 36]
hbm4  = [2048, 13.0, 3.3, 36, 48]

# 归一化到 HBM3E=1 作对比基线
norm_hbm3e = [1.0] * len(metrics)
norm_hbm4  = [hbm4[i] / hbm3e[i] for i in range(len(metrics))]

x = np.arange(len(metrics))
width = 0.36

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6), dpi=300)

# 左图：绝对值对比
b1 = ax1.bar(x - width/2, hbm3e, width, label='HBM3E', color='#8DA0CB', edgecolor='black', linewidth=0.6)
b2 = ax1.bar(x + width/2, hbm4,  width, label='HBM4',  color='#FC8D62', edgecolor='black', linewidth=0.6)
ax1.set_yscale('log')
ax1.set_xticks(x)
ax1.set_xticklabels(metrics, fontsize=9)
ax1.set_ylabel('Value (log scale)', fontsize=10)
ax1.set_title('HBM3E vs HBM4: Absolute Specifications', fontsize=12, fontweight='bold')
ax1.legend(loc='upper right', fontsize=10)
ax1.grid(axis='y', alpha=0.3, linestyle='--')
for i, (v3e, v4) in enumerate(zip(hbm3e, hbm4)):
    ax1.text(i - width/2, v3e * 1.15, str(v3e), ha='center', fontsize=8)
    ax1.text(i + width/2, v4  * 1.15, str(v4),  ha='center', fontsize=8, fontweight='bold', color='#B4290F')

# 右图：倍数对比（HBM3E=1x baseline）
colors = ['#66C2A5' if v <= 1.5 else '#FC8D62' if v <= 2.5 else '#E41A1C' for v in norm_hbm4]
b3 = ax2.bar(x, norm_hbm4, color=colors, edgecolor='black', linewidth=0.6, width=0.6)
ax2.axhline(y=1.0, color='#999999', linestyle='--', linewidth=1, label='HBM3E baseline (1.0x)')
ax2.set_xticks(x)
ax2.set_xticklabels(metrics, fontsize=9)
ax2.set_ylabel('HBM4 / HBM3E ratio', fontsize=10)
ax2.set_title('HBM4 Gain over HBM3E (multiplier)', fontsize=12, fontweight='bold')
ax2.set_ylim(0, 3.5)
ax2.legend(loc='upper left', fontsize=10)
ax2.grid(axis='y', alpha=0.3, linestyle='--')
for i, v in enumerate(norm_hbm4):
    ax2.text(i, v + 0.08, f'{v:.2f}x', ha='center', fontsize=10, fontweight='bold')

plt.suptitle('HBM3E vs HBM4 Generation Comparison — Samsung/SK hynix/Micron (2026)',
             fontsize=13, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig('hbm_generation_compare.png', dpi=300, bbox_inches='tight')
print('Saved: hbm_generation_compare.png')
