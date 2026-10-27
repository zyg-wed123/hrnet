# -*- coding: utf-8 -*-
import os
import sys
from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('graphics', 'multisamples', '0')
from kivy.core.window import Window
from kivy.core.text import LabelBase
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.graphics import Color, Rectangle, Line
from kivy.clock import Clock
import sqlite3
from datetime import datetime
import math, shutil

# 判断是否在 Android 环境
IS_ANDROID = hasattr(sys, 'getandroidapilevel')

# 字体注册：Android 上使用打包的字体文件，Windows 上使用系统字体
if IS_ANDROID:
    # Android：使用打包在 assets 里的字体
    FONT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ziti.ttf")
    LabelBase.register(name="SimSun", fn_regular=FONT_FILE)
    LabelBase.register(name="SimHei", fn_regular=FONT_FILE)
else:
    # Windows：使用系统字体
    FONT_DIR = "C:/Windows/Fonts"
    if not os.path.exists(FONT_DIR):
        FONT_DIR = os.path.dirname(os.path.abspath(__file__))
    for name, fn in [("SimSun", "simsun.ttc"), ("SimHei", "simhei.ttf")]:
        p = os.path.join(FONT_DIR, fn)
        if os.path.exists(p):
            LabelBase.register(name=name, fn_regular=p)

# 数据库路径：Android 上保存在应用私有目录（手机本地），Windows 上保存在脚本同目录
def get_db_path():
    if IS_ANDROID:
        # Android 应用私有数据目录，持久保存
        from android.storage import app_storage_path
        return os.path.join(app_storage_path(), "hr_net.db")
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "hr_net.db")

DB_PATH = get_db_path()

# ===== 全局缩放：让手机界面字体/控件/图片更大更清晰 =====
# 以窗口较短的边为基准，短边约 340 逻辑像素时缩放 1.35，
# 手机竖屏短边更小时进一步放大；1.35 基础放大让手机端明显更大、更易点击
def _base_short():
    try:
        return min(Window.width, Window.height)
    except Exception:
        return 340.0
SCALE = max(1.35, (340.0 / _base_short()) * 1.4)
# 字号缩放（保留小数），控件高度/间距用整数
def FS(px):   return px * SCALE          # 字号
def D(px):    return int(px * SCALE)     # 尺寸/高度/间距

def white_popup(title, msg, size=(0.8,0.3)):
    """白底提示弹窗"""
    p=Popup(title="",separator_height=0,background='',size_hint=size)
    box=BoxLayout(orientation="vertical",padding=D(10),spacing=D(6))
    with box.canvas.before:
        Color(1,1,1,1); r=Rectangle(pos=box.pos,size=box.size)
    box.bind(pos=lambda *a:setattr(r,'pos',box.pos),size=lambda *a:setattr(r,'size',box.size))
    box.add_widget(Label(text=title,font_name="SimHei",font_size=FS(16),bold=True,color=(0,0,0,1),size_hint_y=0.25))
    ml=Label(text=msg,font_name="SimSun",font_size=FS(14),color=(0.2,0.2,0.2,1),size_hint_y=0.55)
    ml.bind(size=lambda *a:setattr(ml,'text_size',(ml.width,None)))
    box.add_widget(ml)
    b=Button(text="确定",font_name="SimSun",font_size=FS(15),size_hint_y=0.2)
    b.bind(on_press=lambda x:p.dismiss())
    box.add_widget(b)
    p.content=box; p.open()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS person (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,birth TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS position_history(id INTEGER PRIMARY KEY AUTOINCREMENT,person_id INTEGER,position TEXT,change_time TEXT,FOREIGN KEY(person_id) REFERENCES person(id))''')
    cur.execute('''CREATE TABLE IF NOT EXISTS relation(id INTEGER PRIMARY KEY AUTOINCREMENT,person_id INTEGER NOT NULL,target_name TEXT NOT NULL,target_pos TEXT,relation_desc TEXT,FOREIGN KEY(person_id) REFERENCES person(id))''')
    conn.commit(); conn.close()

def get_relation_network(start_person_id):
    conn = sqlite3.connect(DB_PATH); cur = conn.cursor()
    cur.execute("SELECT id,name FROM person WHERE id=?", (start_person_id,))
    start = cur.fetchone()
    if not start: conn.close(); return {}, []
    nodes={}; edges=[]; visited=set()
    def gpi(pid):
        c=conn.cursor()
        c.execute("SELECT name FROM person WHERE id=?",(pid,)); nr=c.fetchone()
        if not nr: return "",""
        pn=nr[0]
        c.execute("SELECT position FROM position_history WHERE person_id=? ORDER BY change_time DESC LIMIT 1",(pid,))
        pr=c.fetchone()
        return pn,(pr[0] if pr else "")
    sn,sp=gpi(start_person_id); nodes[sn]={"id":start_person_id,"pos":sp}
    def dfs(pid):
        if pid in visited: return
        visited.add(pid)
        cur.execute("SELECT target_name,target_pos,relation_desc FROM relation WHERE person_id=? ORDER BY id ASC",(pid,))
        for tn,tp,rd in cur.fetchall():
            src_name,_=gpi(pid)
            cur.execute("SELECT id FROM person WHERE name=?",(tn,)); tr=cur.fetchone()
            if tr:
                tpid=tr[0]; nn,np_=gpi(tpid)
                nodes[nn]={"id":tpid,"pos":np_}; edges.append((src_name,nn,rd)); dfs(tpid)
            else:
                nodes[tn]={"id":None,"pos":tp}; edges.append((src_name,tn,rd))
    dfs(start_person_id); conn.close(); return nodes,edges


class PositionChartWidget(Widget):
    def __init__(self, pos_list, **kwargs):
        super().__init__(**kwargs)
        self.pos_list=pos_list
        with self.canvas.before:
            Color(1,1,1,1); self.bg=Rectangle(pos=self.pos,size=self.size)
        self.bind(pos=self._bg,size=self._bg); self.bind(size=self.draw)
    def _bg(self,*a): self.bg.pos=self.pos; self.bg.size=self.size
    def pym(self,s):
        try:
            s=str(s).strip()
            for sep in ["年","月",".","-","/"," "]: s=s.replace(sep,".")
            parts=[q for q in s.split(".") if q!=""]
            y=int(parts[0]); m=int(parts[1])
            if y<100: y+=1900
            return datetime(y,m,1).timestamp()
        except: return None
    def draw(self,*a):
        w,h=self.size
        if w<50 or h<50 or not self.pos_list: return
        self.canvas.clear()
        data=[]
        for pos,ts in self.pos_list:
            t=self.pym(ts)
            if t is not None:
                dt=datetime.fromtimestamp(t)
                data.append((dt.year,dt.month,pos))
        if not data: return
        data.sort(key=lambda d: datetime(d[0],d[1],1).timestamp())
        # 去重：相邻相同职位只保留一个
        dedup=[]
        for d in data:
            if not dedup or d[2]!=dedup[-1][2]:
                dedup.append(d)
        data=dedup
        self.clear_widgets()
        x_left=w*0.15; x_right=w*0.85
        axis_y=h*0.30; dot_y=h*0.62
        with self.canvas:
            Color(0,0,0,1)
            Line(points=[x_left,axis_y,x_right,axis_y],width=1.2)
            Line(points=[x_right-10,axis_y+5,x_right,axis_y,x_right-10,axis_y-5],width=1.2)
            Line(points=[x_left,axis_y,x_left,h-15],width=1.2)
            Line(points=[x_left-5,h-25,x_left,h-15,x_left+5,h-25],width=1.2)
        n=len(data); step=min(D(200),(x_right-x_left)/max(n-1,1))
        for i,(y,mo,pos) in enumerate(data):
            nx=x_left+i*step
            with self.canvas:
                Color(0.85,0.1,0.1,1)
                Line(circle=(nx,dot_y,D(6)),width=1.5)
            self.add_widget(Label(text=pos,pos=(nx-D(75),dot_y+D(12)),size=(D(170),D(32)),font_size=FS(16),bold=True,color=(0,0,0,1),font_name="SimHei",halign="center"))
            self.add_widget(Label(text=f"{y}年{mo}月",pos=(nx-D(55),axis_y-D(30)),size=(D(130),D(28)),font_size=FS(15),color=(0,0,0,1),font_name="SimSun",halign="center"))


class RelationGraphWidget(Widget):
    def __init__(self,nodes,edges,root_name,screen_ref,**kwargs):
        super().__init__(**kwargs)
        self.size_hint=(1,1)
        self.nodes=nodes; self.edges=edges; self.root_name=root_name; self.screen_ref=screen_ref
        with self.canvas.before:
            Color(1,1,1,1); self.bg=Rectangle(pos=self.pos,size=self.size)
        self.bind(pos=self._bg,size=self._bg)
        self.bind(size=self.draw)
    def _bg(self,*a): self.bg.pos=self.pos; self.bg.size=self.size
    def draw(self,*a):
        w,h=self.size
        if w<50 or h<50 or not self.nodes: return
        self.canvas.clear()
        self.clear_widgets()
        children={}
        for s,t,d in self.edges: children.setdefault(s,[]).append(t)
        root=self.root_name if self.root_name in self.nodes else list(self.nodes.keys())[0]
        if root is None: return
        level={root:0}; order=[root]
        for s in order:
            for t in children.get(s,[]):
                if t not in level: level[t]=level[s]+1; order.append(t)
        for n in self.nodes:
            if n not in level: level[n]=0
        maxlv=max(level.values()) if level else 0
        x_left=w*0.15; x_right=w*0.85
        def x_at(lv):
            if maxlv==0: return (x_left+x_right)/2
            return x_left+(x_right-x_left)*lv/maxlv
        # 整体上移（Kivy坐标，正值=往上）
        y_shift = h*0.70
        y_top=h*0.95 + y_shift; y_bot=h*0.40 + y_shift
        cy=(y_top+y_bot)/2.0
        pc={}
        def place(node,y0,y1):
            ch=children.get(node,[])
            if not ch:
                pc[node]=(x_at(level[node]),(y0+y1)/2); return (y0+y1)/2
            n=len(ch); band=(y1-y0)/n; cys=[]
            for i,c in enumerate(ch): cys.append(place(c,y0+i*band,y0+(i+1)*band))
            ny=sum(cys)/len(cys); pc[node]=(x_at(level[node]),ny); return ny
        place(root,y_top,y_bot)
        for n in self.nodes:
            if n not in pc: pc[n]=(x_at(0),cy)
        # 连线
        with self.canvas:
            Color(0.3,0.6,0.8,1)
            for s,t,d in self.edges:
                if s in pc and t in pc:
                    x1,y1=pc[s]; x2,y2=pc[t]; mx=(x1+x2)/2
                    Line(bezier=[x1,y1,mx,y1,mx,y2,x2,y2],width=1.2)
        # 关系描述（放线段中点）
        for s,t,d in self.edges:
            if s in pc and t in pc and d.strip():
                x1,y1=pc[s]; x2,y2=pc[t]
                lx=(x1+x2)/2; ly=(y1+y2)/2
                self.add_widget(Label(text=d,pos=(lx-D(35),ly-D(15)),size=(D(130),D(30)),font_size=FS(15),bold=True,color=(0.8,0,0,1),font_name="SimHei"))
        # 人名圆节点
        for name,(x,y) in pc.items():
            with self.canvas:
                Color(0.9,0.95,1,1); Line(circle=(x,y,D(32)),width=1.2)
            self.add_widget(Label(text=name,pos=(x-D(65),y-D(16)),size=(D(130),D(32)),font_size=FS(15),bold=True,color=(0,0,0,1),font_name="SimHei"))


class DirBrowserPopup(Popup):
    """白底文件/文件夹浏览弹窗"""
    def __init__(self,start_path,on_select,is_file_mode=False,**kwargs):
        super().__init__(**kwargs)
        self.title=""; self.separator_height=0; self.background=''
        self.size_hint=(0.95,0.85); self.on_select=on_select
        self.is_file_mode=is_file_mode
        self.selected_file=None
        self.cur=start_path if os.path.isdir(start_path) else os.path.expanduser("~")
        root=BoxLayout(orientation="vertical",padding=D(10),spacing=D(5))
        with root.canvas.before:
            Color(1,1,1,1); self._bg=Rectangle(pos=root.pos,size=root.size)
        root.bind(pos=lambda *a:setattr(self._bg,'pos',root.pos),size=lambda *a:setattr(self._bg,'size',root.size))
        # 顶部路径行
        top=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(5))
        up=Button(text="上级",font_name="SimSun",font_size=FS(14),size_hint_x=0.15); up.bind(on_press=self._go_up)
        self.path_lbl=Label(text=self.cur,font_name="SimSun",font_size=FS(13),color=(0,0,0,1),size_hint_x=0.7,halign="left",valign="middle")
        self.path_lbl.bind(size=lambda *a:setattr(self.path_lbl,'text_size',self.path_lbl.size))
        top.add_widget(up); top.add_widget(self.path_lbl)
        root.add_widget(top)
        # 列表
        self.sv=ScrollView()
        self.list_box=GridLayout(cols=1,spacing=D(3),size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        self.sv.add_widget(self.list_box)
        root.add_widget(self.sv)
        # 底部按钮
        bot=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(54),spacing=D(8))
        ok_text="选择此文件夹" if not is_file_mode else "取消"
        self.ok_btn=Button(text=ok_text,font_name="SimSun",font_size=FS(15))
        if is_file_mode:
            self.ok_btn.disabled=True
        self.ok_btn.bind(on_press=self._choose)
        cancel=Button(text="取消",font_name="SimSun",font_size=FS(15)); cancel.bind(on_press=self.dismiss)
        bot.add_widget(self.ok_btn); bot.add_widget(cancel)
        root.add_widget(bot)
        self.content=root
        self._load()
    def _load(self):
        self.list_box.clear_widgets()
        self.path_lbl.text=self.cur
        self.selected_file=None
        if self.is_file_mode: self.ok_btn.disabled=True
        try:
            dirs=sorted([d for d in os.listdir(self.cur) if os.path.isdir(os.path.join(self.cur,d))])
            files=sorted([f for f in os.listdir(self.cur) if os.path.isfile(os.path.join(self.cur,f)) and f.lower().endswith((".xlsx",".xls"))])
        except: dirs=[]; files=[]
        for d in dirs:
            b=Button(text="📁 "+d,font_name="SimSun",font_size=FS(14),size_hint_y=None,height=D(48))
            path=os.path.join(self.cur,d)
            b.bind(on_press=lambda x,p=path:self._enter(p))
            self.list_box.add_widget(b)
        for f in files:
            b=Button(text="📄 "+f,font_name="SimSun",font_size=FS(14),size_hint_y=None,height=D(48),background_color=(0.9,0.95,1,1))
            path=os.path.join(self.cur,f)
            b.bind(on_press=lambda x,p=path,n=f:self._pick_file(p,n))
            self.list_box.add_widget(b)
    def _go_up(self,x):
        p=os.path.dirname(self.cur)
        if p and os.path.isdir(p): self.cur=p; self._load()
    def _enter(self,p):
        self.cur=p; self._load()
    def _pick_file(self,path,name):
        self.selected_file=path
        self.ok_btn.disabled=False
        self.ok_btn.text="选择: "+name
    def _choose(self,x):
        if self.is_file_mode and self.selected_file:
            self.on_select(self.selected_file); self.dismiss()
        elif not self.is_file_mode:
            self.on_select(self.cur); self.dismiss()


class FileDialogPopup(Popup):
    """白底文件路径选择弹窗"""
    def __init__(self,title_text,default_dir,default_name,on_confirm,is_export=True,**kwargs):
        super().__init__(**kwargs)
        self.title=""; self.separator_height=0; self.background=''
        self.size_hint=(0.92,None); self.height=D(380)
        self.on_confirm=on_confirm; self.is_export=is_export
        layout=BoxLayout(orientation="vertical",padding=D(12),spacing=D(8))
        with layout.canvas.before:
            Color(1,1,1,1); self._bg=Rectangle(pos=layout.pos,size=layout.size)
        layout.bind(pos=lambda *a:setattr(self._bg,'pos',layout.pos),size=lambda *a:setattr(self._bg,'size',layout.size))
        layout.add_widget(Label(text=title_text,font_name="SimHei",font_size=FS(16),bold=True,color=(0,0,0,1),size_hint_y=None,height=D(34)))
        # 文件夹行
        r1=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(48),spacing=D(6))
        r1.add_widget(Label(text="文件夹:",font_name="SimSun",font_size=FS(14),size_hint_x=0.13,color=(0,0,0,1)))
        self.dir_in=TextInput(text=default_dir,font_name="SimSun",font_size=FS(14),size_hint_x=0.67,multiline=False)
        r1.add_widget(self.dir_in)
        bb=Button(text="浏览",font_name="SimSun",font_size=FS(14),size_hint_x=0.20); bb.bind(on_press=self._browse)
        r1.add_widget(bb)
        layout.add_widget(r1)
        # 文件名行
        r2=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(48),spacing=D(6))
        r2.add_widget(Label(text="文件名:",font_name="SimSun",font_size=FS(14),size_hint_x=0.13,color=(0,0,0,1)))
        self.name_in=TextInput(text=default_name,font_name="SimSun",font_size=FS(14),size_hint_x=0.87,multiline=False)
        r2.add_widget(self.name_in)
        layout.add_widget(r2)
        # 按钮
        btn=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(54),spacing=D(10))
        bok=Button(text="确定",font_name="SimSun",font_size=FS(16)); bok.bind(on_press=self._ok)
        bcancel=Button(text="取消",font_name="SimSun",font_size=FS(16)); bcancel.bind(on_press=self.dismiss)
        btn.add_widget(bok); btn.add_widget(bcancel)
        layout.add_widget(btn)
        self.content=layout
    def _browse(self,x):
        def _sel(p):
            self.dir_in.text=p
        DirBrowserPopup(self.dir_in.text or os.path.expanduser("~"),_sel).open()
    def _ok(self,x):
        d=self.dir_in.text.strip(); n=self.name_in.text.strip()
        if d and n:
            ext=".xlsx"
            if not n.endswith(ext): n=n+ext
            full=os.path.join(d,n)
            self.on_confirm(full); self.dismiss()


class EditPersonPopup(Popup):
    def __init__(self,pid,screen_ref,**kwargs):
        super().__init__(**kwargs)
        self.pid=pid; self.screen_ref=screen_ref
        self.title=""; self.size_hint=(0.95,None); self.height=D(500)
        self.separator_height=0
        self.background=''
        layout=BoxLayout(orientation="vertical",padding=[D(8),0,D(8),D(8)],spacing=D(4))
        with layout.canvas.before:
            Color(1,1,1,1); self._popbg=Rectangle(pos=layout.pos,size=layout.size)
        layout.bind(pos=lambda *a:setattr(self._popbg,'pos',layout.pos),size=lambda *a:setattr(self._popbg,'size',layout.size))
        def pt(lbl,sx=0.12,fs=15):
            return Label(text=lbl,size_hint_x=sx,font_name="SimSun",font_size=FS(fs),halign="left",color=(0,0,0,1))
        def ti(fs=15,hint="",sx=1.0):
            return TextInput(font_name="SimSun",font_size=FS(fs),height=D(42),hint_text=hint,size_hint_x=sx,multiline=False)
        # 六行结构：姓名/年月/职位+日期/关系1/关系2/关系3
        r1=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r1.add_widget(pt("姓名",0.10)); self.name_in=ti(); r1.add_widget(self.name_in)
        r2=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r2.add_widget(pt("年月",0.10)); self.birth_in=ti(); r2.add_widget(self.birth_in)
        r3=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r3.add_widget(pt("职位",0.08)); self.pos_in=ti(sx=0.42); r3.add_widget(self.pos_in)
        r3.add_widget(pt("日期",0.07)); self.pos_date_in=ti(hint="日期",sx=0.43); r3.add_widget(self.pos_date_in)
        r4=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r4.add_widget(pt("关系1",0.10))
        self._e_r1n=ti(hint="姓名",sx=0.30); r4.add_widget(self._e_r1n)
        self._e_r1p=ti(hint="职位",sx=0.30); r4.add_widget(self._e_r1p)
        self._e_r1d=ti(hint="关系",sx=0.30); r4.add_widget(self._e_r1d)
        r5=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r5.add_widget(pt("关系2",0.10))
        self._e_r2n=ti(hint="姓名",sx=0.30); r5.add_widget(self._e_r2n)
        self._e_r2p=ti(hint="职位",sx=0.30); r5.add_widget(self._e_r2p)
        self._e_r2d=ti(hint="关系",sx=0.30); r5.add_widget(self._e_r2d)
        r6=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(46),spacing=D(3))
        r6.add_widget(pt("关系3",0.10))
        self._e_r3n=ti(hint="姓名",sx=0.30); r6.add_widget(self._e_r3n)
        self._e_r3p=ti(hint="职位",sx=0.30); r6.add_widget(self._e_r3p)
        self._e_r3d=ti(hint="关系",sx=0.30); r6.add_widget(self._e_r3d)
        for r in [r1,r2,r3,r4,r5,r6]: layout.add_widget(r)
        self.r_in=[(self._e_r1n,self._e_r1p,self._e_r1d),
                   (self._e_r2n,self._e_r2p,self._e_r2d),
                   (self._e_r3n,self._e_r3p,self._e_r3d)]
        bb=BoxLayout(size_hint_y=None,height=D(56),spacing=D(10),padding=[0,D(8),0,0])
        bs=Button(text="保存修改",font_name="SimSun",font_size=FS(16)); bs.bind(on_press=self.save_edit)
        bc=Button(text="取消",font_name="SimSun",font_size=FS(16)); bc.bind(on_press=self.dismiss)
        bb.add_widget(bs); bb.add_widget(bc); layout.add_widget(bb)
        self.content=layout; self.load()
    def load(self):
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        cur.execute("SELECT name,birth FROM person WHERE id=?",(self.pid,))
        p=cur.fetchone(); self.name_in.text=p[0]; self.birth_in.text=p[1]
        cur.execute("SELECT position,change_time FROM position_history WHERE person_id=? ORDER BY change_time DESC LIMIT 1", (self.pid,))
        pd=cur.fetchone()
        if pd: self.pos_in.text=pd[0]; self.pos_date_in.text=pd[1]
        cur.execute("SELECT target_name,target_pos,relation_desc FROM relation WHERE person_id=? ORDER BY id ASC LIMIT 3",(self.pid,))
        for i,r in enumerate(cur.fetchall()):
            if i<3: self.r_in[i][0].text=r[0]; self.r_in[i][1].text=r[1]; self.r_in[i][2].text=r[2]
        c.close()
    def save_edit(self,x):
        name=self.name_in.text.strip()
        if not name: return
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        cur.execute("UPDATE person SET name=?,birth=? WHERE id=?",(name,self.birth_in.text.strip(),self.pid))
        pos=self.pos_in.text.strip(); pd=self.pos_date_in.text.strip()
        if pos and pd:
            cur.execute("INSERT INTO position_history(person_id,position,change_time) VALUES (?,?,?)",(self.pid,pos,pd))
        cur.execute("DELETE FROM relation WHERE person_id=?",(self.pid,))
        for tn,tp,td in self.r_in:
            n=tn.text.strip()
            if n: cur.execute("INSERT INTO relation(person_id,target_name,target_pos,relation_desc) VALUES (?,?,?,?)",(self.pid,n,tp.text.strip(),td.text.strip()))
        c.commit(); c.close(); self.dismiss()
        self.screen_ref.load_person_list(); self.screen_ref.refresh_graph_by_pid(self.pid)


class PersonRow(BoxLayout):
    _COLS=(0.4,0.55,0.55,1.3,1.35,1.35,1.35)
    def __init__(self,data,on_click,**kwargs):
        super().__init__(orientation="horizontal",size_hint_y=None,height=D(50),spacing=1,**kwargs)
        self.pid=data["id"]; self.on_click=on_click; self._selected=False
        with self.canvas.before:
            self._col=Color(1,1,1,1); self._bg=Rectangle(pos=self.pos,size=self.size)
        self.bind(pos=lambda *a:setattr(self._bg,'pos',self.pos),size=lambda *a:setattr(self._bg,'size',self.size))
        def cell(txt,bold=False,sx=1.0):
            return Label(text=str(txt),size_hint_x=sx,font_name="SimSun",font_size=FS(14),bold=bold,color=(0,0,0,1))
        def relc(n,p,d,sx=1.0):
            txt = "|".join([x for x in [str(n),str(p),str(d)] if x])
            return Label(text=txt,size_hint_x=sx,font_name="SimSun",font_size=FS(13),color=(0,0,0,1),halign="center")
        self.add_widget(cell(data["id"],bold=True,sx=self._COLS[0]))
        self.add_widget(cell(data["name"],sx=self._COLS[1]))
        self.add_widget(cell(data["birth"],sx=self._COLS[2]))
        self.add_widget(cell(data["positions"],sx=self._COLS[3]))
        self.add_widget(relc(data["r1_name"],data["r1_pos"],data["r1_desc"],sx=self._COLS[4]))
        self.add_widget(relc(data["r2_name"],data["r2_pos"],data["r2_desc"],sx=self._COLS[5]))
        self.add_widget(relc(data["r3_name"],data["r3_pos"],data["r3_desc"],sx=self._COLS[6]))
    def set_selected(self,sel):
        self._selected=sel
        if sel: self._col.rgba=(0.78,0.88,1.0,1)
        else: self._col.rgba=(1,1,1,1)
    def on_touch_down(self,touch):
        if self.collide_point(*touch.pos):
            self.on_click(self.pid); return True
        return super().on_touch_down(touch)


class MainScreen(Screen):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        root=BoxLayout(orientation="vertical",padding=0,spacing=0)
        with root.canvas.before:
            Color(1,1,1,1); self._r=Rectangle(size=root.size,pos=root.pos)
        root.bind(size=lambda i,v:setattr(self._r,'size',i.size),pos=lambda i,v:setattr(self._r,'pos',i.pos))

        top_panel=BoxLayout(orientation="vertical",size_hint_y=0.64,spacing=D(6),padding=[0,D(16),0,0])
        mid_panel=BoxLayout(orientation="vertical",size_hint_y=0.19,spacing=D(2))
        bot_panel=BoxLayout(orientation="vertical",size_hint_y=0.17,spacing=D(2))

        # ===== 表单区：3行，左半 姓名/年月/职位，右半 关系1/2/3 =====
        form=BoxLayout(orientation="vertical",size_hint_y=None,height=D(202),spacing=D(2),padding=[D(4),D(10),D(4),0])
        def mk_ti(fs=14,hint=""):
            return TextInput(font_name="SimSun",font_size=FS(fs),height=D(42),hint_text=hint,size_hint_x=1)

        self.name_in=mk_ti(); self.birth_in=mk_ti(); self.pos_in=mk_ti()
        self.pos_date_in=mk_ti(hint="日期")
        self.r1n=mk_ti(hint="姓名"); self.r1p=mk_ti(hint="职位"); self.r1d=mk_ti(hint="关系")
        self.r2n=mk_ti(hint="姓名"); self.r2p=mk_ti(hint="职位"); self.r2d=mk_ti(hint="关系")
        self.r3n=mk_ti(hint="姓名"); self.r3p=mk_ti(hint="职位"); self.r3d=mk_ti(hint="关系")

        # 左半：标签统一宽 0.18，输入框统一占剩余
        def left_cell(lbl_text, inp):
            h=BoxLayout(orientation="horizontal",size_hint_x=0.45,spacing=D(2))
            h.add_widget(Label(text=lbl_text,size_hint_x=0.22,font_name="SimSun",font_size=FS(15),halign="right",color=(0,0,0,1)))
            inp.size_hint_x=0.78; h.add_widget(inp)
            return h
        # 右半：关系标签 + 3个带提示的输入框
        def right_cell(lbl_text, n_w, p_w, d_w):
            h=BoxLayout(orientation="horizontal",size_hint_x=0.55,spacing=D(1))
            h.add_widget(Label(text=lbl_text,size_hint_x=0.15,font_name="SimSun",font_size=FS(14),halign="right",color=(0,0,0,1)))
            n_w.size_hint_x=0.28; p_w.size_hint_x=0.28; d_w.size_hint_x=0.29
            h.add_widget(n_w); h.add_widget(p_w); h.add_widget(d_w)
            return h

        row1=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(44),spacing=D(2))
        row1.add_widget(left_cell("姓名",self.name_in))
        row1.add_widget(right_cell("关系1",self.r1n,self.r1p,self.r1d))
        row2=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(44),spacing=D(2))
        row2.add_widget(left_cell("年月",self.birth_in))
        row2.add_widget(right_cell("关系2",self.r2n,self.r2p,self.r2d))
        row3=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(44),spacing=D(2))
        # 职位行左半：职位标签+职位输入+日期输入，和上面两行对齐
        left3=BoxLayout(orientation="horizontal",size_hint_x=0.45,spacing=D(2))
        left3.add_widget(Label(text="职位",size_hint_x=0.22,font_name="SimSun",font_size=FS(15),halign="right",color=(0,0,0,1)))
        self.pos_in.size_hint_x=0.42; left3.add_widget(self.pos_in)
        self.pos_date_in.size_hint_x=0.36; left3.add_widget(self.pos_date_in)
        row3.add_widget(left3)
        row3.add_widget(right_cell("关系3",self.r3n,self.r3p,self.r3d))
        for w in [row1,row2,row3]: form.add_widget(w)

        # 按钮行
        bb=BoxLayout(orientation="horizontal",spacing=D(2),size_hint_y=None,height=D(50))
        def ab(t,f):
            b=Button(text=t,font_name="SimSun",font_size=FS(16)); b.bind(on_press=f); bb.add_widget(b)
        ab("新增",self.do_save); ab("查询",self.do_query); ab("编辑",self.do_edit)
        ab("删除",self.do_delete); ab("导出",self.do_export); ab("导入",self.do_import)
        form.add_widget(bb)
        top_panel.add_widget(form)

        # ===== 列表区：全宽 =====
        list_panel=BoxLayout(orientation="vertical",spacing=0)
        list_panel.add_widget(Label(text="人员列表",font_name="SimHei",font_size=FS(18),bold=True,color=(0,0,0,1),size_hint_y=None,height=D(34)))
        hdr=BoxLayout(orientation="horizontal",size_hint_y=None,height=D(44),spacing=1)
        with hdr.canvas.before:
            Color(0.9,0.9,0.9,1); self._hbg=Rectangle(pos=hdr.pos,size=hdr.size)
        hdr.bind(pos=lambda *a:setattr(self._hbg,'pos',hdr.pos),size=lambda *a:setattr(self._hbg,'size',hdr.size))
        C=(0.4,0.55,0.55,1.3,1.35,1.35,1.35)
        def hcell(txt,sx):
            return Label(text=txt,size_hint_x=sx,font_name="SimHei",font_size=FS(16),bold=True,color=(0,0,0,1))
        hdr.add_widget(hcell("ID",C[0])); hdr.add_widget(hcell("姓名",C[1]))
        hdr.add_widget(hcell("年月",C[2])); hdr.add_widget(hcell("职位",C[3]))
        hdr.add_widget(hcell("关系1",C[4])); hdr.add_widget(hcell("关系2",C[5]))
        hdr.add_widget(hcell("关系3",C[6]))
        list_panel.add_widget(hdr)
        scroll=ScrollView()
        self.list_box=GridLayout(cols=1,spacing=1,size_hint_y=None)
        self.list_box.bind(minimum_height=self.list_box.setter("height"))
        scroll.add_widget(self.list_box); list_panel.add_widget(scroll)
        top_panel.add_widget(list_panel)
        root.add_widget(top_panel)

        # ===== 关系网 =====
        mid_panel.add_widget(Label(text="关系网",font_name="SimHei",font_size=FS(18),bold=True,color=(0,0,0,1),size_hint_y=None,height=D(30)))
        self.graph_box=BoxLayout(size_hint_y=0.95)
        mid_panel.add_widget(self.graph_box)
        root.add_widget(mid_panel)

        # ===== 职位变迁 =====
        bot_panel.add_widget(Label(text="职位变迁",font_name="SimHei",font_size=FS(18),bold=True,color=(0,0,0,1),size_hint_y=None,height=D(30)))
        self.chart_box=BoxLayout(size_hint_y=0.95)
        bot_panel.add_widget(self.chart_box)
        root.add_widget(bot_panel)

        self.add_widget(root); self.selected_pid=None; self.load_person_list()

    def load_person_list(self,keyword=""):
        self.list_box.clear_widgets()
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        if keyword.strip():
            cur.execute('''SELECT DISTINCT p.id,p.name,p.birth FROM person p LEFT JOIN relation r ON p.id=r.person_id WHERE p.name LIKE ? OR r.target_name LIKE ? ORDER BY p.id ASC''',(f"%{keyword}%",f"%{keyword}%"))
        else:
            cur.execute("SELECT id,name,birth FROM person ORDER BY id ASC")
        all_p=cur.fetchall(); self.person_full_data=[]
        for pid,name,birth in all_p:
            cur.execute("SELECT position,change_time FROM position_history WHERE person_id=? ORDER BY change_time ASC",(pid,))
            pos_list=cur.fetchall()
            # 职位列：只显示最新职位，多个加 I
            if pos_list:
                latest_pos=pos_list[-1][0]
                pos_text=latest_pos + ("|" if len(pos_list)>1 else "")
            else:
                pos_text=""
            cur.execute("SELECT target_name,target_pos,relation_desc FROM relation WHERE person_id=? ORDER BY id ASC LIMIT 3",(pid,))
            rels=cur.fetchall()
            r1=rels[0] if len(rels)>0 else ("","","")
            r2=rels[1] if len(rels)>1 else ("","","")
            r3=rels[2] if len(rels)>2 else ("","","")
            d={"id":pid,"name":name,"birth":birth,"positions":pos_text,
               "r1_name":r1[0],"r1_pos":r1[1],"r1_desc":r1[2],
               "r2_name":r2[0],"r2_pos":r2[1],"r2_desc":r2[2],
               "r3_name":r3[0],"r3_pos":r3[1],"r3_desc":r3[2]}
            self.person_full_data.append(d)
            self.list_box.add_widget(PersonRow(d,self.on_person_click))
        c.close()
        if all_p:
            self.selected_pid=all_p[0][0]
        self._apply_selection()
        if all_p:
            self.refresh_graph_by_pid(self.selected_pid)
        else:
            self.graph_box.clear_widgets(); self.chart_box.clear_widgets()

    def _apply_selection(self):
        for row in self.list_box.children:
            try: row.set_selected(row.pid==self.selected_pid)
            except: pass

    def on_person_click(self,pid):
        self.selected_pid=pid; self._apply_selection(); self.refresh_graph_by_pid(pid)

    def refresh_graph_by_pid(self,pid):
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        cur.execute("SELECT position,change_time FROM position_history WHERE person_id=? ORDER BY change_time ASC",(pid,))
        pos_data=cur.fetchall()
        cur.execute("SELECT name FROM person WHERE id=?",(pid,))
        rn=cur.fetchone(); root_name=rn[0] if rn else None
        nodes,edges=get_relation_network(pid); c.close()
        self.graph_box.clear_widgets()
        gw=RelationGraphWidget(nodes,edges,root_name,self)
        self.graph_box.add_widget(gw)
        self._gw=gw
        Clock.schedule_once(lambda dt: gw.draw(), 0.3)
        self.chart_box.clear_widgets()
        cw=PositionChartWidget(pos_data)
        self.chart_box.add_widget(cw)
        self._cw=cw
        Clock.schedule_once(lambda dt: cw.draw(), 0.3)

    def do_edit(self,x):
        if self.selected_pid is None:
            white_popup("提示","请先在右侧列表选一条人员"); return
        EditPersonPopup(self.selected_pid,self).open()

    def do_delete(self,x):
        if self.selected_pid is None:
            white_popup("提示","请先选择要删除的人员"); return
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        cur.execute("DELETE FROM person WHERE id=?",(self.selected_pid,))
        cur.execute("DELETE FROM position_history WHERE person_id=?",(self.selected_pid,))
        cur.execute("DELETE FROM relation WHERE person_id=?",(self.selected_pid,))
        c.commit(); c.close()
        self.selected_pid=None; self.clear_form(); self.load_person_list()

    def do_save(self,x):
        name=self.name_in.text.strip()
        if not name:
            white_popup("提示","姓名不能为空"); return
        birth=self.birth_in.text.strip(); pos=self.pos_in.text.strip()
        pd=self.pos_date_in.text.strip() or datetime.now().strftime("%Y年%m月")
        rels=[(self.r1n.text.strip(),self.r1p.text.strip(),self.r1d.text.strip()),
              (self.r2n.text.strip(),self.r2p.text.strip(),self.r2d.text.strip()),
              (self.r3n.text.strip(),self.r3p.text.strip(),self.r3d.text.strip())]
        c=sqlite3.connect(DB_PATH); cur=c.cursor()
        cur.execute("SELECT id FROM person WHERE name=?",(name,)); ex=cur.fetchone()
        if ex:
            pid=ex[0]
            if pos: cur.execute("INSERT INTO position_history(person_id,position,change_time) VALUES (?,?,?)",(pid,pos,pd))
        else:
            cur.execute("INSERT INTO person(name,birth) VALUES (?,?)",(name,birth))
            pid=cur.lastrowid
            if pos: cur.execute("INSERT INTO position_history(person_id,position,change_time) VALUES (?,?,?)",(pid,pos,pd))
        for tn,tp,td in rels:
            if tn: cur.execute("INSERT INTO relation(person_id,target_name,target_pos,relation_desc) VALUES (?,?,?,?)",(pid,tn,tp,td))
        c.commit(); c.close(); self.clear_form(); self.load_person_list()

    def do_query(self,x): self.load_person_list(self.name_in.text.strip())

    def do_export(self,x):
        """导出 Excel"""
        try:
            from openpyxl import Workbook
            wb=Workbook(); ws=wb.active; ws.title="人员列表"
            cols=["id","name","birth","positions","r1_name","r1_pos","r1_desc","r2_name","r2_pos","r2_desc","r3_name","r3_pos","r3_desc"]
            headers=["ID","姓名","年月","职位","关系1姓名","关系1职位","关系1描述","关系2姓名","关系2职位","关系2描述","关系3姓名","关系3职位","关系3描述"]
            ws.append(headers)
            for d in self.person_full_data:
                ws.append([d.get(c,"") for c in cols])
            if IS_ANDROID:
                # Android：保存到应用私有目录
                out_path = os.path.join(os.path.dirname(DB_PATH), "hrnet_export.xlsx")
                wb.save(out_path)
                white_popup("导出成功", f"已保存到应用数据目录:\nhrnet_export.xlsx")
            else:
                # Windows：弹出文件选择对话框
                def _do(full):
                    try:
                        wb.save(full)
                        white_popup("导出成功", f"已保存到{full}")
                    except Exception as e:
                        white_popup("导出失败", str(e))
                FileDialogPopup("导出人员列表(Excel)", os.path.dirname(DB_PATH), "人员列表.xlsx", _do, is_export=True).open()
        except Exception as e:
            white_popup("导出失败", str(e))

    def do_import(self,x):
        """导入 Excel"""
        if IS_ANDROID:
            white_popup("提示", "手机版暂不支持导入功能\n请在电脑端导入后同步数据")
            return
        def _do(full):
            try:
                from openpyxl import load_workbook
                wb=load_workbook(full); ws=wb.active
                dst=sqlite3.connect(DB_PATH); dc=dst.cursor()
                rows=list(ws.iter_rows(min_row=2,values_only=True))
                for row in rows:
                    if not row or not row[1]: continue
                    name=str(row[1] or "").strip(); birth=str(row[2] or "").strip()
                    if not name: continue
                    dc.execute("SELECT id FROM person WHERE name=?",(name,))
                    r=dc.fetchone()
                    if r: pid=r[0]
                    else:
                        dc.execute("INSERT INTO person(name,birth) VALUES (?,?)",(name,birth)); pid=dc.lastrowid
                    positions=str(row[3] or "").split("|")
                    for pos in positions:
                        pos=pos.strip()
                        if pos:
                            dc.execute("SELECT 1 FROM position_history WHERE person_id=? AND position=?",(pid,pos))
                            if not dc.fetchone():
                                dc.execute("INSERT INTO position_history(person_id,position,change_time) VALUES (?,?)",(pid,pos,""))
                    for i in range(3):
                        rn=row[4+i*3]; rp=row[5+i*3]; rd=row[6+i*3]
                        if rn and str(rn).strip():
                            dc.execute("SELECT 1 FROM relation WHERE person_id=? AND target_name=? AND relation_desc=?",(pid,str(rn).strip(),str(rd or "").strip()))
                            if not dc.fetchone():
                                dc.execute("INSERT INTO relation(person_id,target_name,target_pos,relation_desc) VALUES (?,?,?,?)",(pid,str(rn).strip(),str(rp or "").strip(),str(rd or "").strip()))
                dst.commit(); dst.close()
                self.load_person_list()
                white_popup("导入成功",f"已从{full}合并导入")
            except Exception as e:
                white_popup("导入失败",str(e))
        DirBrowserPopup(os.path.dirname(DB_PATH),_do,is_file_mode=True).open()

    def clear_form(self):
        for w in [self.name_in,self.birth_in,self.pos_in,self.pos_date_in,
                  self.r1n,self.r1p,self.r1d,self.r2n,self.r2p,self.r2d,
                  self.r3n,self.r3p,self.r3d]:
            w.text=""


class HRNetApp(App):
    def build(self):
        self.title="HRNet人事关系管理系统"
        sm=ScreenManager(); sm.add_widget(MainScreen(name="main")); return sm

if __name__=="__main__":
    init_db(); HRNetApp().run()
