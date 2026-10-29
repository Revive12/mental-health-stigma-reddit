"""Rebuild Fig. 2 and four supplementary figures from archived statistics.

Run: python scripts/plot_figures.py
No inferential model, bootstrap or multiple-testing adjustment is rerun.
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
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

DATA, OUT = ROOT / 'source_data', ROOT / 'figures'
OUT.mkdir(exist_ok=True)
CODES = list('ABCDEFG')
ALL_CODES = list('ABCDEFGH')
LABELS = dict(zip(ALL_CODES, [
    'responsibility', 'social distance', 'anger', 'helping', 'pity',
    'coercive segregation', 'fear', 'non-stigmatizing',
]))
GROUPS = ['ALL', 'MH', 'General']
GROUP_NAMES = {'ALL': 'All', 'MH': 'MH', 'General': 'General'}
GROUP_COLORS = {'ALL': '#52616B', 'MH': '#176B9A', 'General': '#B15E28'}
INK, MUTED = '#20262B', '#59636A'
EXCESS_CMAP = colors.LinearSegmentedColormap.from_list(
    'blue_neutral_brown', ['#2166AC', '#F7F7F7', '#B35806'])

arial = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
if arial.exists():
    font_manager.fontManager.addfont(arial)
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 8, 'axes.labelsize': 8, 'xtick.labelsize': 7.5,
    'ytick.labelsize': 7.5, 'legend.fontsize': 7.5,
    'text.color': INK, 'axes.labelcolor': INK,
    'xtick.color': INK, 'ytick.color': INK,
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.linewidth': .65, 'xtick.major.width': .6, 'ytick.major.width': .6,
    'pdf.fonttype': 42, 'ps.fonttype': 42, 'svg.fonttype': 'none',
    'savefig.facecolor': 'white',
})

def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write(name, rows):
    with (DATA / name).open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

COUNTS = read('RQ2_transition_counts.csv')
STATS = read('RQ2_transition_stats.csv')
AG = read('RQ2_transition_AG_stats.csv')
CONTRASTS = read('RQ2_community_differences.csv')
COUNT_INDEX = {(r['group'], r['parent'], r['child']): r for r in COUNTS}
STAT_INDEX = {(r['group'], r['parent'], r['child']): r for r in STATS}
AG_INDEX = {(r['group'], r['parent'], r['child']): r for r in AG}
TOTAL_PAIRS = {g: sum(int(r['N']) for r in COUNTS if r['group'] == g) for g in GROUPS}

# Validate the denominator and D against the full eight-category count matrices.
for g in GROUPS:
    for a in ALL_CODES:
        row_total = sum(int(COUNT_INDEX[g, a, b]['N']) for b in ALL_CODES)
        for b in ALL_CODES:
            cell = COUNT_INDEX[g, a, b]
            marginal = sum(int(COUNT_INDEX[g, aa, b]['N']) for aa in ALL_CODES) / TOTAL_PAIRS[g]
            expected = int(cell['N']) / row_total - marginal
            assert np.isclose(expected, float(STAT_INDEX[g, a, b]['D']))

BINARY = []
for g in GROUPS:
    for stigma in [False, True]:
        rr = [r for r in COUNTS if r['group'] == g and (r['parent'] != 'H') == stigma]
        denominator = sum(int(r['N']) for r in rr)
        numerator = sum(int(r['N']) for r in rr if r['child'] != 'H')
        BINARY.append(dict(group=g, comment_stigma=int(stigma),
                           stigmatizing_replies=numerator, all_replies=denominator,
                           percentage=100 * numerator / denominator))
BINARY_INDEX = {(r['group'], r['comment_stigma']): r for r in BINARY}
write('displayed_binary_probabilities.csv', BINARY)

CONDITIONAL = []
for a in CODES:
    for b in CODES:
        r = AG_INDEX['ALL', a, b]
        CONDITIONAL.append(dict(comment=a, comment_label=LABELS[a], reply=b,
                                reply_label=LABELS[b], count=int(r['N_ab']),
                                row_n=int(r['N_a_plus']), percentage=100 * float(r['P_ab'])))
write('displayed_conditional_attributions.csv', CONDITIONAL)
assert sum(r['count'] for r in CONDITIONAL) == 4760
for a in CODES:
    assert np.isclose(sum(r['percentage'] for r in CONDITIONAL if r['comment'] == a), 100)

excess_rows = []
for r in STATS:
    c = COUNT_INDEX[r['group'], r['parent'], r['child']]
    excess_rows.append(dict(group=r['group'], comment=r['parent'],
        comment_label=LABELS[r['parent']], reply=r['child'], reply_label=LABELS[r['child']],
        count=int(c['N']), all_replies_to_comment_label=int(c['Na_plus']),
        conditional_reply_probability=float(c['P']), marginal_reply_frequency=float(c['q']),
        excess_pp=100 * float(r['D']), ci_low_pp=100 * float(r['ci_lo']),
        ci_high_pp=100 * float(r['ci_hi']), testable=int(r['testable']),
        p_two_sided_wald=r['p_wald'], p_BH_adjusted=r['q_BH']))
write('displayed_complete_excess_matrices.csv', excess_rows)
write('displayed_Fig2b_excess_probabilities.csv',
      [r for r in excess_rows if r['group'] == 'ALL' and r['comment'] in CODES and r['reply'] in CODES])
eligible = [r for r in CONTRASTS if r['testable'] == '1']
assert len(eligible) == 36
assert sum(float(r['q_BH']) < .05 for r in eligible) == 10
assert sum(r['testable'] == '1' for r in STATS) == 161
write('displayed_community_differences.csv', [dict(
    comment=r['parent'], comment_label=LABELS[r['parent']], reply=r['child'],
    reply_label=LABELS[r['child']], MH_probability=float(r['P_MH']),
    General_probability=float(r['P_General']), difference_pp=100*float(r['Delta']),
    ci_low_pp=100*float(r['ci_lo']), ci_high_pp=100*float(r['ci_hi']),
    p_BH_adjusted=float(r['q_BH'])) for r in eligible])
(DATA / 'attribution_labels_fixed.json').write_text(json.dumps(LABELS, indent=2) + '\n')

LAYOUT_AUDIT = {}

def save(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bounds = fig.bbox
    outside = []
    for txt in fig.findobj(matplotlib.text.Text):
        if not txt.get_visible() or not txt.get_text().strip():
            continue
        bb = txt.get_window_extent(renderer=renderer)
        if bb.width and bb.height and (bb.x0 < -2 or bb.y0 < -2 or bb.x1 > bounds.width+2 or bb.y1 > bounds.height+2):
            outside.append(txt.get_text())
    LAYOUT_AUDIT[name] = dict(size_mm=[round(v*25.4, 2) for v in fig.get_size_inches()],
                            text_outside_canvas=outside)
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(OUT / f'{name}.{ext}', dpi=300)
    fig.savefig(OUT / f'{name}_preview.png', dpi=170)
    plt.close(fig)

def letter(fig, label, x, y):
    fig.text(x, y, label, weight='bold', fontsize=10, va='top')

def mark_cell(ax, x, y, row):
    if row['testable'] == '0':
        ax.plot(x, y, marker='x', ms=4, mew=.9, color='#20262B', linestyle='None')
    elif float(row['q_BH']) < .05:
        # Identical marker for every significant cell, legible on dark/light fills.
        ax.plot(x, y, marker='o', ms=3.3, mfc='#20262B', mec='white', mew=.65, linestyle='None')

def symbol_legend(fig, xy, fontsize=7.2):
    handles = [
        Line2D([], [], marker='o', ms=4, mfc=INK, mec='white', mew=.65,
               linestyle='None', label='BH-adjusted p < 0.05'),
        Line2D([], [], marker='x', ms=4, color=INK, linestyle='None',
               label='Not eligible for testing'),
    ]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=xy, ncol=2,
               frameon=False, handlelength=1, columnspacing=2, fontsize=fontsize)

def heatmap(ax, group, codes, norm, full_names=False):
    matrix = np.array([[100*float(STAT_INDEX[group, a, b]['D']) for b in codes] for a in codes])
    n = len(codes)
    im = ax.pcolormesh(np.arange(n+1)-.5, np.arange(n+1)-.5, matrix,
                       cmap=EXCESS_CMAP, norm=norm, edgecolors='white', linewidth=.45,
                       shading='flat', rasterized=False)
    ax.set_xlim(-.5, n-.5)
    ax.set_ylim(n-.5, -.5)
    ax.set_aspect('equal')
    ax.set_xticks(range(n), codes)
    ax.set_yticks(range(n), [f'{a}  {LABELS[a]}' for a in codes] if full_names else codes)
    ax.tick_params(length=0, pad=5)
    for i, a in enumerate(codes):
        for j, b in enumerate(codes):
            mark_cell(ax, j, i, STAT_INDEX[group, a, b])
    for spine in ax.spines.values():
        spine.set_visible(False)
    return im

def attribution_key(fig, top=.135, fontsize=7.3):
    columns = [list('ABC'), list('DEF'), list('GH')]
    for x, codes in zip([.08, .37, .74], columns):
        for j, code in enumerate(codes):
            fig.text(x, top - j*.026, f'{code}  {LABELS[code]}', fontsize=fontsize, va='top')

def plot_binary_supplement():
    fig = plt.figure(figsize=(180/25.4, 95/25.4))
    ax = fig.add_axes([.14, .27, .80, .57])
    xs = np.array([0, 1.1])
    for j, g in enumerate(GROUPS):
        yy = [BINARY_INDEX[g, s]['percentage'] for s in [0, 1]]
        xx = xs+(j-1)*.21
        ax.bar(xx, yy, width=.18, color=GROUP_COLORS[g], zorder=3)
        for x, y in zip(xx, yy):
            ax.text(x, y+.3, f'{y:.2f}', ha='center', fontsize=8)
    ax.set_xticks(xs, ['non-stigmatizing', 'stigmatizing'])
    ax.set_xlabel('Comment', labelpad=7)
    ax.set_ylabel('Stigmatizing replies (%)', labelpad=7)
    ax.set_ylim(0, 15)
    ax.set_yticks([0, 5, 10, 15])
    ax.set_axisbelow(True)
    ax.grid(axis='y', color='#E5E8EA', linewidth=.5)
    fig.legend(handles=[Patch(facecolor=GROUP_COLORS[g], label=GROUP_NAMES[g]) for g in GROUPS],
               loc='upper center', bbox_to_anchor=(.55,.965), ncol=3, frameon=False)
    save(fig, 'Supplementary_reply_stigma_by_community')

def plot_conditional_supplement():
    fig = plt.figure(figsize=(180/25.4, 110/25.4))
    ax = fig.add_axes([.34, .14, .48, .78545])
    matrix = np.array([[100*float(AG_INDEX['ALL',a,b]['P_ab']) for b in CODES] for a in CODES])
    im = ax.pcolormesh(np.arange(8)-.5, np.arange(8)-.5, matrix,
                       cmap='Blues', vmin=0, vmax=60, edgecolors='white', linewidth=.65,
                       shading='flat', rasterized=False)
    ax.set_xlim(-.5, 6.5)
    ax.set_ylim(6.5, -.5)
    ax.set_aspect('equal')
    for i in range(7):
        for j in range(7):
            ax.text(j, i, f'{matrix[i,j]:.1f}', ha='center', va='center', fontsize=8,
                    color='white' if matrix[i,j] > 35 else '#183B53')
    ax.set_xticks(range(7), CODES)
    ax.set_yticks(range(7), [f"{a}  {LABELS[a]}\n(n = {int(AG_INDEX['ALL',a,a]['N_a_plus']):,})" for a in CODES])
    ax.tick_params(length=0, pad=6)
    ax.set_xlabel('Reply attribution', labelpad=6)
    ax.set_ylabel('Comment attribution', labelpad=9)
    for spine in ax.spines.values(): spine.set_visible(False)
    cb = fig.colorbar(im, cax=fig.add_axes([.855,.14,.022,.78545]), ticks=[0,20,40,60])
    cb.solids.set_rasterized(False)
    cb.outline.set_visible(False)
    cb.set_label('Composition of stigmatizing replies (%)', labelpad=7)
    save(fig, 'Supplementary_conditional_attributions')

def plot_contrast_supplement():
    fig = plt.figure(figsize=(180/25.4, 180/25.4))
    subsets = [
        [r for r in eligible if r['parent'] in CODES and r['child'] in CODES],
        [r for r in eligible if r['parent'] == 'H' or r['child'] == 'H'],
    ]
    assert [len(x) for x in subsets] == [21, 15]
    for j, rows in enumerate(subsets):
        xx = [.13, .62][j]
        ax = fig.add_axes([xx,.245,.34,.685])
        letter(fig, 'ab'[j], xx-.10, .97)
        for i, r in enumerate(rows):
            y = 20-i
            d, lo, hi = [100*float(r[k]) for k in ['Delta','ci_lo','ci_hi']]
            sig = float(r['q_BH']) < .05
            ax.errorbar(d, y, xerr=np.array([[d-lo],[hi-d]]), fmt='o', ms=4,
                        mfc='#176B9A' if sig else 'white', mec='#176B9A' if sig else '#626C73',
                        mew=.9, ecolor='#176B9A' if sig else '#8B9399', elinewidth=1,
                        capsize=2, capthick=.7, zorder=3)
        ax.set_yticks([20-i for i in range(len(rows))], [f"{r['parent']} → {r['child']}" for r in rows])
        ax.set_ylim(-.8,20.8)
        ax.set_xlim(-7.5,9.5)
        ax.set_xticks([-6,-3,0,3,6,9])
        ax.axvline(0, color='#8A949B', lw=.8, ls=(0,(3,3)), zorder=1)
        ax.grid(axis='x', color='#E5E8EA', lw=.45, zorder=0)
        ax.set_axisbelow(True)
        ax.tick_params(axis='y', length=0, pad=5)
        ax.spines['left'].set_visible(False)
        ax.set_xlabel('MH − General\n(percentage points)', labelpad=5)
    fig.legend(handles=[
        Line2D([],[],marker='o',mfc='#176B9A',mec='#176B9A',linestyle='None',ms=4,label='BH-adjusted p < 0.05'),
        Line2D([],[],marker='o',mfc='white',mec='#626C73',linestyle='None',ms=4,label='BH-adjusted p ≥ 0.05'),
    ], loc='lower center', bbox_to_anchor=(.52,.145), ncol=2, frameon=False)
    attribution_key(fig, .125)
    save(fig, 'Supplementary_community_differences')

def plot_full_matrices():
    fig = plt.figure(figsize=(180/25.4, 125/25.4))
    norm = colors.TwoSlopeNorm(vmin=-14,vcenter=0,vmax=14)
    for j, g in enumerate(GROUPS):
        x = .072+j*.312
        letter(fig, 'abc'[j], x-.034, .97)
        fig.text(x+.126,.943,GROUP_NAMES[g],ha='center',fontsize=8)
        ax = fig.add_axes([x,.475,.252,.3629])
        im = heatmap(ax,g,ALL_CODES,norm)
        ax.set_xlabel('Reply label',labelpad=5)
        if j == 0: ax.set_ylabel('Comment label',labelpad=6)
    cb = fig.colorbar(im,cax=fig.add_axes([.285,.35,.43,.023]),orientation='horizontal',ticks=[-14,-7,0,7,14])
    cb.solids.set_rasterized(False)
    cb.outline.set_visible(False)
    cb.set_label('Difference from overall reply frequency (percentage points)',labelpad=5)
    symbol_legend(fig,(.52,.235),7)
    attribution_key(fig,.19)
    save(fig, 'Supplementary_complete_excess_matrices')

if __name__ == '__main__':
    plot_binary_supplement()
    plot_conditional_supplement()
    plot_contrast_supplement()
    plot_full_matrices()
    (ROOT/'layout_audit.json').write_text(json.dumps(LAYOUT_AUDIT,indent=2)+'\n')
    inputs = ['RQ2_transition_counts.csv','RQ2_transition_stats.csv','RQ2_transition_AG_stats.csv',
              'RQ2_community_differences.csv','RQ2_community_differences_crossauth.csv']
    provenance = {
        'source_directory': 'source_data',
        'source_sha256': {n:hashlib.sha256((DATA/n).read_bytes()).hexdigest() for n in inputs},
        'fixed_labels': LABELS, 'total_pairs': TOTAL_PAIRS,
        'both_stigmatizing_pairs': 4760,
        'excess_definition': 'P(reply=b | comment=a), denominator includes H, minus P(reply=b) in the full group',
        'excess_BH_family': '161 eligible cells jointly across ALL, MH and General; supplied adjusted values retained',
        'community_contrast_definition': 'P_MH(reply=b | comment=a) minus P_General(reply=b | comment=a), including H in each row denominator',
        'community_contrast_BH_family': '36 eligible contrasts, supplied adjusted values retained',
        'bootstrap': 'Existing 2,000 whole-post bootstrap resamples; pointwise 95% intervals',
        'new_inferential_analyses': False,
        'main_color_limits_pp': [-8,8], 'complete_matrices_color_limits_pp':[-14,14],
        'format': 'Vector PDF and SVG, 300-dpi PNG, 170-dpi preview PNG',
        'software': {'matplotlib':matplotlib.__version__,'numpy':np.__version__},
    }
    (DATA/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({'figures':list(LAYOUT_AUDIT),'layout_issues':LAYOUT_AUDIT},indent=2))
