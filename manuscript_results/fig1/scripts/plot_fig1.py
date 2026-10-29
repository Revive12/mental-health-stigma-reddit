"""Rebuild Fig. 1 and Supplementary Fig. S1 from frozen RQ1 counts.
Run with Python, numpy and matplotlib. No statistical estimates are added.
"""
from pathlib import Path
import csv
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.mplconfig'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import colors, font_manager
from matplotlib.patches import Patch
from matplotlib.transforms import blended_transform_factory

DATA, OUT = ROOT / 'source_data', ROOT / 'figures'
OUT.mkdir(exist_ok=True)

def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))

rows = {r['scope']: r for r in read('RQ1_counts.csv')}
mapping = sorted(read('subreddit_group_mapping.csv'),
                 key=lambda r: (r['community_type'] != 'MH', r['subreddit'].casefold()))
names = [r['subreddit'] for r in mapping]
groups = [r['community_type'] for r in mapping]
CODES = list('ABCDEFG')
LABELS = json.loads((DATA / 'attribution_labels_fixed.json').read_text())
counts = np.array([[int(float(rows[n]['n_' + c])) for c in CODES] for n in names])
totals = np.array([int(rows[n]['S']) for n in names])
assert len(names) == 16 and groups.count('MH') == 5 and groups.count('General') == 11
assert np.array_equal(counts.sum(axis=1), totals)
for group in ['ALL', 'MH', 'General']:
    selected = [n for n, g in zip(names, groups) if group == 'ALL' or g == group]
    for field in ['posts', 'comments', 'S', 'H', 'n_stigma_posts'] + ['n_' + c for c in CODES]:
        assert sum(int(float(rows[n][field])) for n in selected) == int(float(rows[group][field]))
shares = np.divide(counts * 100., totals[:, None],
                   out=np.full(counts.shape, np.nan), where=totals[:, None] > 0)
assert np.allclose(shares[totals > 0].sum(axis=1), 100)
assert [n for n, s in zip(names, totals) if s == 0] == ['r4r']
assert int(rows['r4r']['posts']) == 3 and int(rows['r4r']['comments']) == 117

with (DATA / 'displayed_Fig1b_composition.csv').open('w', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['subreddit', 'community_type', 'code', 'attribution', 'count',
                     'stigmatizing_comments', 'percentage', 'numeric_label_shown'])
    for i, n in enumerate(names):
        for j, c in enumerate(CODES):
            v = shares[i, j]
            writer.writerow([n, groups[i], c, LABELS[c], int(counts[i, j]), int(totals[i]),
                             '' if totals[i] == 0 else v, bool(totals[i] and v >= 6)])

for filename, numerator, denominator in [('displayed_Fig1a_posts.csv', 'n_stigma_posts', 'posts'),
                                         ('displayed_S1_comments.csv', 'S', 'comments')]:
    with (DATA / filename).open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['community_type', 'numerator', 'denominator', 'percentage'])
        for group in ['MH', 'General']:
            num, den = int(float(rows[group][numerator])), int(rows[group][denominator])
            writer.writerow([group, num, den, num / den * 100])

arial = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
if arial.exists(): font_manager.fontManager.addfont(arial)
INK, MUTED = '#20262B', '#59636A'
ATTR_COLORS = ['#4477AA', '#66CCEE', '#228833', '#CCBB44', '#EE6677', '#AA3377', '#BBBBBB']
GROUP_COLORS = {'MH': '#17669A', 'General': '#9B4D27'}
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 7.5, 'axes.labelsize': 7.5, 'xtick.labelsize': 7, 'ytick.labelsize': 7,
    'text.color': INK, 'axes.labelcolor': INK, 'xtick.color': INK, 'ytick.color': INK,
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.linewidth': .6,
    'xtick.major.width': .6, 'ytick.major.width': .6,
    'pdf.fonttype': 42, 'svg.fonttype': 'none', 'savefig.facecolor': 'white',
})

def contrast(color):
    r, g, b = colors.to_rgb(color)
    return 'white' if .2126 * r + .7152 * g + .0722 * b < .53 else INK

def prevalence(ax, numerator, denominator, unit, xlabel, xmax, ticks):
    order = ['MH', 'General']
    values = [100 * float(rows[g][numerator]) / float(rows[g][denominator]) for g in order]
    ax.barh([1, 0], values, height=.46, color=[GROUP_COLORS[g] for g in order], zorder=3)
    for y, value in zip([1, 0], values):
        ax.text(value + xmax * .012, y, f'{value:.2f}%', va='center', fontsize=8)
    ax.set_yticks([1, 0], [f"Mental health (MH)\n(n = {int(rows['MH'][denominator]):,} {unit})",
                          f"General\n(n = {int(rows['General'][denominator]):,} {unit})"])
    ax.tick_params(axis='y', length=0, pad=7)
    ax.set_ylim(-.58, 1.58)
    ax.set_xlim(0, xmax)
    ax.set_xticks(ticks)
    ax.set_xlabel(xlabel, labelpad=5)
    ax.spines['left'].set_visible(False)
    ax.set_axisbelow(True)
    ax.grid(axis='x', color='#E5E8EA', lw=.45)

def save(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside = []
    for text in fig.findobj(matplotlib.text.Text):
        if not text.get_visible() or not text.get_text().strip(): continue
        bb = text.get_window_extent(renderer=renderer)
        if bb.width and bb.height and (bb.x0 < -2 or bb.y0 < -2 or
                                      bb.x1 > fig.bbox.width + 2 or bb.y1 > fig.bbox.height + 2):
            outside.append(text.get_text())
    assert not outside, outside
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(OUT / f'{name}.{ext}', dpi=300)
    fig.savefig(OUT / f'{name}_preview.png', dpi=190)
    plt.close(fig)

fig = plt.figure(figsize=(180 / 25.4, 180 / 25.4))
fig.text(.025, .978, 'a', fontsize=10, weight='bold', va='top')
ax_a = fig.add_axes([.33, .855, .59, .112])
prevalence(ax_a, 'n_stigma_posts', 'posts', 'posts',
           'Posts containing at least one stigmatizing comment (%)', 25, [0, 5, 10, 15, 20, 25])

fig.text(.025, .768, 'b', fontsize=10, weight='bold', va='top')
ax = fig.add_axes([.33, .185, .56, .558])
y = np.arange(16, dtype=float)
y[5:] += .65
for i, name in enumerate(names):
    if totals[i] == 0:
        ax.text(50, y[i], 'No stigmatizing comments', ha='center', va='center',
                fontsize=7, color=MUTED, fontstyle='italic')
        continue
    left = 0
    for j, value in enumerate(shares[i]):
        ax.barh(y[i], value, left=left, height=.66, color=ATTR_COLORS[j],
                edgecolor='white', linewidth=.35, zorder=3)
        if value >= 6:
            ax.text(left + value / 2, y[i], f'{value:.1f}', ha='center', va='center',
                    fontsize=6.5, color=contrast(ATTR_COLORS[j]), zorder=4)
        left += value
ax.set_yticks(y, ['r/' + n for n in names])
for tick, group in zip(ax.get_yticklabels(), groups): tick.set_color(GROUP_COLORS[group])
ax.set_ylim(y[-1] + .7, -.7)
ax.set_xlim(0, 100)
ax.set_xticks(np.arange(0, 101, 20))
ax.tick_params(axis='y', length=0, pad=6)
ax.spines['left'].set_visible(False)
ax.set_axisbelow(True)
ax.grid(axis='x', color='#E5E8EA', lw=.45)
ax.set_xlabel('Attribution composition among stigmatizing comments (%)', labelpad=5)
trans = blended_transform_factory(ax.transAxes, ax.transData)
for i, total in enumerate(totals):
    ax.text(1.16, y[i], f'{total:,}', transform=trans, ha='right', va='center', fontsize=7, clip_on=False)
ax.text(1.16, 1.035, 'n', transform=ax.transAxes, ha='right', va='bottom', fontsize=7.5, fontstyle='italic')
for start, end, label, group in [(0, 4, 'Mental health (MH)', 'MH'), (5, 15, 'General', 'General')]:
    lo, hi = y[start] - .36, y[end] + .36
    ax.plot([-.46, -.48, -.48, -.46], [lo, lo, hi, hi], transform=trans,
            color=GROUP_COLORS[group], lw=.8, clip_on=False)
    ax.text(-.52, (lo + hi) / 2, label, transform=trans, rotation=90, ha='center', va='center',
            color=GROUP_COLORS[group], fontsize=7.5, weight='bold', clip_on=False)
fig.legend(handles=[Patch(facecolor=color, label=LABELS[c]) for c, color in zip(CODES, ATTR_COLORS)],
           loc='lower center', bbox_to_anchor=(.55, .032), ncol=4, frameon=False,
           handlelength=1.3, handletextpad=.55, columnspacing=1.5, labelspacing=.7, fontsize=7)
save(fig, 'Fig1_revised')

fig = plt.figure(figsize=(180 / 25.4, 63 / 25.4))
ax = fig.add_axes([.33, .29, .59, .59])
prevalence(ax, 'S', 'comments', 'comments', 'Stigmatizing comments (%)', 5, [0, 1, 2, 3, 4, 5])
save(fig, 'Supplementary_Fig_S1_comment_prevalence')

provenance = {
    'source': 'Frozen RQ1_counts.csv; base subreddit rows and ALL/MH/General summaries',
    'source_sha256': hashlib.sha256((DATA / 'RQ1_counts.csv').read_bytes()).hexdigest(),
    'source_mapping_sha256': hashlib.sha256((DATA / 'subreddit_group_mapping.csv').read_bytes()).hexdigest(),
    'Fig1a_denominator': 'All retained posts within each community group',
    'Fig1b_denominator': 'Stigmatizing comments within each individual subreddit',
    'S1_denominator': 'All retained comments within each community group',
    'subreddit_order': names, 'attribution_labels': LABELS, 'attribution_colors': dict(zip(CODES, ATTR_COLORS)),
    'zero_event_row': 'r/r4r: 3 posts, 117 comments, 0 stigmatizing comments; composition undefined',
    'segment_label_threshold_percent': 6, 'inference': 'Descriptive percentages; no confidence intervals or tests added',
    'validation': '16 subreddit sums match ALL/MH/General; A-G counts sum to S; positive-denominator compositions sum to 100%',
}
(DATA / 'provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({'outputs': ['Fig1_revised', 'Supplementary_Fig_S1_comment_prevalence'],
                  'subreddits': len(names), 'stigmatizing_comments': int(totals.sum())}, indent=2))
