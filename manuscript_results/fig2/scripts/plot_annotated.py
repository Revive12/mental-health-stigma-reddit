"""Draw the annotated alternative to Fig. 2. No clustering or new inference.
Run: python scripts/plot_annotated.py
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
from matplotlib.patches import Rectangle

DATA, OUT = ROOT/'source_data', ROOT/'figures'
OUT.mkdir(exist_ok=True)
LABELS = json.loads((DATA/'attribution_labels_fixed.json').read_text())
CODES = list('ABCDEFG')

def read(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

rows = read('displayed_Fig2b_excess_probabilities.csv')
index = {(r['comment'],r['reply']):r for r in rows}
binary = {int(r['comment_stigma']):r for r in read('displayed_binary_probabilities.csv') if r['group']=='ALL'}
assert len(rows)==49
assert sum(int(r['testable']) for r in rows)==48
assert sum(r['testable']=='1' and float(r['p_BH_adjusted'])<.05 for r in rows)==45
assert index['B','D']['testable']=='0'
diagonal = [index[c,c] for c in CODES]
assert all(float(r['excess_pp'])>0 and float(r['p_BH_adjusted'])<.001 for r in diagonal)
off_diagonal = [r for r in rows if r['comment']!=r['reply']]
assert len(off_diagonal)==42
top = sorted(off_diagonal, key=lambda r:(-float(r['excess_pp']),r['comment'],r['reply']))[:3]
assert [(r['comment'],r['reply']) for r in top]==[('D','A'),('B','C'),('F','A')]
assert all(r['testable']=='1' and float(r['p_BH_adjusted'])<.05 for r in top)
rank = {(r['comment'],r['reply']):i+1 for i,r in enumerate(top)}
for r in top:
    assert float(r['ci_low_pp'])<float(r['excess_pp'])<float(r['ci_high_pp'])
with (DATA/'annotation_values.csv').open('w',newline='') as f:
    columns=['annotation','comment','comment_label','reply','reply_label','excess_pp','ci_low_pp','ci_high_pp','p_BH_adjusted']
    writer=csv.DictWriter(f,fieldnames=columns)
    writer.writeheader()
    for i,r in enumerate(top,1): writer.writerow({'annotation':i,**{c:r[c] for c in columns[1:]}})

arial = Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"
if arial.exists(): font_manager.fontManager.addfont(arial)
INK, MUTED, BLUE = '#20262B','#59636A','#176B9A'
plt.rcParams.update({
    'font.family':'DejaVu Sans',
    'font.size':7.5,'axes.labelsize':7.5,'xtick.labelsize':7,'ytick.labelsize':7,
    'text.color':INK,'axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,
    'axes.spines.top':False,'axes.spines.right':False,
    'axes.linewidth':.6,'xtick.major.width':.6,'ytick.major.width':.6,
    'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white',
})
fig=plt.figure(figsize=(180/25.4,155/25.4))

# a: the same descriptive proportions and denominators as the prior version.
fig.text(.025,.972,'a',fontsize=10,weight='bold',va='top')
ax_a=fig.add_axes([.29,.795,.64,.15])
ax_a.barh([1,0],[float(binary[s]['percentage']) for s in [0,1]],height=.43,
          color=['#A4ADB4',BLUE],zorder=3)
for y,s in zip([1,0],[0,1]):
    value=float(binary[s]['percentage'])
    ax_a.text(value+.23,y,f'{value:.2f}%',va='center',fontsize=8)
ax_a.set_yticks([1,0],[f"non-stigmatizing comment\n(n = {int(binary[0]['all_replies']):,} replies)",
                       f"stigmatizing comment\n(n = {int(binary[1]['all_replies']):,} replies)"])
ax_a.tick_params(axis='y',length=0,pad=7)
ax_a.set_xlim(0,14)
ax_a.set_ylim(-.55,1.55)
ax_a.set_xticks([0,5,10])
ax_a.set_xlabel('Stigmatizing replies (%)',labelpad=4)
ax_a.spines['left'].set_visible(False)
ax_a.set_axisbelow(True)
ax_a.grid(axis='x',color='#E5E8EA',lw=.5)

# b: complete A-G matrix. Annotations never remove or re-estimate cells.
fig.text(.025,.712,'b',fontsize=10,weight='bold',va='top')
ax=fig.add_axes([.29,.258,.36,.4180645])
matrix=np.array([[float(index[a,b]['excess_pp']) for b in CODES] for a in CODES])
cmap=colors.LinearSegmentedColormap.from_list('blue_neutral_brown',['#2166AC','#F7F7F7','#B35806'])
im=ax.pcolormesh(np.arange(8)-.5,np.arange(8)-.5,matrix,cmap=cmap,
                 norm=colors.TwoSlopeNorm(vmin=-8,vcenter=0,vmax=8),
                 edgecolors='white',linewidth=.5,shading='flat',rasterized=False)
ax.set_xlim(-.5,6.5)
ax.set_ylim(6.5,-.5)
ax.set_aspect('equal')
ax.set_xticks(range(7),CODES)
ax.set_yticks(range(7),[f'{a}  {LABELS[a]}' for a in CODES])
ax.tick_params(length=0,pad=5)
ax.set_xlabel('Reply attribution',labelpad=5)
ax.set_ylabel('Comment attribution',labelpad=8)
for spine in ax.spines.values(): spine.set_visible(False)
for i,a in enumerate(CODES):
    for j,b in enumerate(CODES):
        r=index[a,b]
        if i==j:
            ax.add_patch(Rectangle((j-.445,i-.445),.89,.89,fill=False,ec=INK,lw=.85,zorder=4))
        if r['testable']=='0':
            ax.plot(j,i,marker='x',ms=3.5,mew=.8,color=INK,ls='None',zorder=5)
        elif float(r['p_BH_adjusted'])<.05:
            ax.plot(j,i,marker='o',ms=2.8,mfc=INK,mec='white',mew=.6,ls='None',zorder=5)
        if (a,b) in rank:
            ax.text(j-.25,i-.25,str(rank[a,b]),ha='center',va='center',fontsize=6,
                    color='white',weight='bold',bbox=dict(boxstyle='circle,pad=.12',fc=BLUE,ec='white',lw=.4),
                    zorder=7)

# Side notes use fixed labels and everyday descriptions instead of new terms.
side_x=.70
fig.text(side_x,.676,'Same attribution',fontsize=7.8,weight='bold',va='top')
low=min(float(r['excess_pp']) for r in diagonal)
high=max(float(r['excess_pp']) for r in diagonal)
fig.text(side_x,.651,f'{low:.2f}–{high:.2f} percentage points\nabove the corresponding\noverall reply frequency',
         fontsize=7,linespacing=1.35,va='top')
fig.add_artist(Line2D([side_x,.965],[.572,.572],transform=fig.transFigure,color='#D3D9DD',lw=.65))
fig.text(side_x,.550,'Different attributions',fontsize=7.8,weight='bold',va='top')
fig.text(side_x,.526,'Three largest differences',fontsize=7,va='top',color=MUTED)
for y,r in zip([.480,.369,.258],top):
    n=rank[r['comment'],r['reply']]
    fig.text(side_x-.014,y-.004,str(n),ha='center',va='center',fontsize=6.5,color='white',weight='bold',
             bbox=dict(boxstyle='circle,pad=.18',fc=BLUE,ec='none'))
    fig.text(side_x+.010,y,f"{LABELS[r['comment']]}\n→ {LABELS[r['reply']]}",fontsize=7.4,
             va='top',linespacing=1.2)
    fig.text(side_x+.010,y-.043,f"+{float(r['excess_pp']):.2f} percentage points",fontsize=7.3,va='top')
    fig.text(side_x+.010,y-.064,f"95% CI {float(r['ci_low_pp']):.2f}–{float(r['ci_high_pp']):.2f}",
             fontsize=7,va='top',color=MUTED)

cb=fig.colorbar(im,cax=fig.add_axes([.29,.155,.36,.014]),orientation='horizontal',ticks=[-8,-4,0,4,8])
cb.solids.set_rasterized(False)
cb.outline.set_visible(False)
cb.ax.tick_params(length=2,pad=2)
cb.set_label('Difference from overall reply frequency\n(percentage points)',fontsize=7.3,labelpad=4)
handles=[Rectangle((0,0),1,1,fill=False,ec=INK,lw=.85,label='Same attribution'),
         Line2D([],[],marker='o',ms=3.3,mfc=INK,mec='white',mew=.6,ls='None',label='BH-adjusted P < 0.05'),
         Line2D([],[],marker='x',ms=3.5,color=INK,ls='None',label='Not eligible for testing')]
fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.52,.018),ncol=3,frameon=False,
           fontsize=6.8,columnspacing=1.7,handlelength=1,handletextpad=.6)

fig.canvas.draw()
renderer=fig.canvas.get_renderer()
outside=[]
for text in fig.findobj(matplotlib.text.Text):
    if not text.get_visible() or not text.get_text().strip(): continue
    bb=text.get_window_extent(renderer=renderer)
    if bb.width and bb.height and (bb.x0< -2 or bb.y0< -2 or bb.x1>fig.bbox.width+2 or bb.y1>fig.bbox.height+2):
        outside.append(text.get_text())
assert not outside, outside
for ext in ['pdf','svg','png']:
    fig.savefig(OUT/f'Fig2_annotated.{ext}',dpi=300)
fig.savefig(OUT/'Fig2_annotated_preview.png',dpi=190)
plt.close(fig)
provenance={
    'title':'Stigma in comments and replies.',
    'scope':'Annotated display of existing estimates; no clustering and no new inference',
    'labels':LABELS,
    'selection':'The three largest observed differences among all 42 off-diagonal A-G cells, ranked before rounding; all three meet the original BH threshold',
    'original_excess_BH_family':161,
    'intervals':'Original pointwise 95% whole-post bootstrap intervals; not adjusted for selection by rank',
    'interpretation':'The ranking is descriptive and does not test differences between ranks.',
    'text_outside_canvas':outside,
    'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.glob('*')
                     if p.is_file() and p.name!='provenance.json'},
}
(DATA/'provenance.json').write_text(json.dumps(provenance,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({'figure':str(OUT/'Fig2_annotated.pdf'),'selected':[(r['comment'],r['reply']) for r in top],
                  'text_outside_canvas':outside},indent=2))
