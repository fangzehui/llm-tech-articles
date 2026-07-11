"""
Vera Rubin vs Blackwell B200 参数雷达图 + 分家 HBM4 分配饼图
数据源：NVIDIA Developer Blog / NVIDIA Vera Rubin NVL72 官方产品页 / Counterpoint Research
生成：300 DPI PNG
"""
import matplotlib.pyplot as plt
import numpy as np

try:
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'SimHei']
    plt.rcParams['axes.unicode_minus'] = False
except Exception:
    pass

# ============ 数据 ============
# 六维参数（以 Blackwell B200 = 1.0 归一）
labels = [
    'Transistors\n(336B vs 208B)',
    'NVFP4 Inference\n(50 vs 10 PF)',
    'HBM Capacity\n(288 vs 192 GB)',
    'HBM Bandwidth\n(22 vs 8 TB/s)',
    'NVLink BW\n(3.6 vs 1.8 TB/s)',
    'NVLink-C2C\n(1.8 vs 0.9 TB/s)'
]
blackwell = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
rubin_raw = [336/208, 50/10, 288/192, 22/8, 3.6/1.8, 1.8/0.9]

# 三家 HBM4 分配（Vera Rubin，取估算中位）
vendors = ['SK hynix', 'Samsung', 'Micron']
share   = [65, 27.5, 7.5]  # % 估算中位
colors_v = ['#4C72B0', '#DD8452', '#55A467']

# ============ 绘图 ============
fig = plt.figure(figsize=(15, 7), dpi=300)

# --- 左：雷达图 ---
angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
angles += angles[:1]
bw_close = blackwell + blackwell[:1]
r_close  = rubin_raw + rubin_raw[:1]

ax1 = plt.subplot(1, 2, 1, projection='polar')
ax1.plot(angles, bw_close, color='#8DA0CB', linewidth=2, label='Blackwell B200 (baseline 1.0x)')
ax1.fill(angles, bw_close, color='#8DA0CB', alpha=0.25)
ax1.plot(angles, r_close, color='#FC8D62', linewidth=2.4, label='Vera Rubin')
ax1.fill(angles, r_close, color='#FC8D62', alpha=0.30)

ax1.set_xticks(angles[:-1])
ax1.set_xticklabels(labels, fontsize=9)
ax1.set_ylim(0, 6)
ax1.set_yticks([1, 2, 3, 4, 5])
ax1.set_yticklabels(['1x', '2x', '3x', '4x', '5x'], fontsize=8)
ax1.grid(True, alpha=0.4)
ax1.set_title('Vera Rubin vs Blackwell B200\n(normalized to Blackwell = 1.0x)',
              fontsize=12, fontweight='bold', pad=25)
ax1.legend(loc='upper right', bbox_to_anchor=(1.35, 1.10), fontsize=9)

# 数值标注（在每个点旁）
for i, (angle, v) in enumerate(zip(angles[:-1], rubin_raw)):
    ax1.text(angle, v + 0.35, f'{v:.2f}x', ha='center', fontsize=9, fontweight='bold',
             color='#B4290F',
             bbox=dict(boxstyle='round,pad=0.15', facecolor='white', edgecolor='none', alpha=0.7))

# --- 右：三家 HBM4 分配饼图 ---
ax2 = plt.subplot(1, 2, 2)
wedges, texts, autotexts = ax2.pie(
    share, labels=vendors, colors=colors_v, autopct='%1.1f%%',
    startangle=90, textprops={'fontsize': 11},
    wedgeprops={'edgecolor': 'white', 'linewidth': 2},
    explode=(0.02, 0.02, 0.05)
)
for at in autotexts:
    at.set_color('white')
    at.set_fontweight('bold')
    at.set_fontsize(12)
ax2.set_title('HBM4 Vendor Allocation for Vera Rubin\n(estimated mid-point, SK 60-70% / Samsung 25-30% / Micron rest)',
              fontsize=12, fontweight='bold', pad=15)

# 添加图例说明
legend_labels = [
    'SK hynix — MR-MUF + 1b DRAM, first HBM4 dev complete 2025-09',
    'Samsung — 4nm base die + 1c DRAM, first mass prod 2026-02-12',
    'Micron — 12H 36GB, mass prod 2026-03-17 GTC 2026'
]
ax2.legend(wedges, legend_labels, loc='lower center', bbox_to_anchor=(0.5, -0.28),
           fontsize=8, frameon=False)

plt.suptitle('Vera Rubin GPU × HBM4 Three-Vendor Certification (Q3 2026 Ship Window)',
             fontsize=13, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig('rubin_vs_blackwell_radar.png', dpi=300, bbox_inches='tight')
print('Saved: rubin_vs_blackwell_radar.png')
