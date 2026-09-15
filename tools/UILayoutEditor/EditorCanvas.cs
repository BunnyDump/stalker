using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Windows.Forms;

namespace HalkUIEditor {
    public sealed class CanvasOptions {
        public bool Grid=true,Snap=true,Names=true,Outlines=true,Cells=true,Background=true,Rulers=true;
        public int GridX=16,GridY=16,Major=4; public float Aspect=1;
        public Color BackgroundColor=Color.FromArgb(20,23,27),GridColor=Color.FromArgb(110,149,165);
        public bool Checker=true; public string ManualBackground;
    }
    public sealed class EditorCanvas : Control {
        public Workspace Workspace; public UiDocument Document; public CanvasOptions Options=new CanvasOptions();
        public string AtlasFile=""; public List<string> Selection=new List<string>();
        public event EventHandler SelectionChanged,EditCommitted,GeometryPreview;
        public event Action<string> StatusChanged,Failure;
        public float Zoom=1; public PointF Pan=new PointF(30,30);
        bool panning,dragging,space,moved;Point mouseStart;PointF worldStart,panStart;string before;
        int resizeHandle=-1;Dictionary<string,RectangleF> initial=new Dictionary<string,RectangleF>();
        ToolTip tooltip=new ToolTip();string hover="";
        public EditorCanvas(){SetStyle(ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer|ControlStyles.UserPaint|ControlStyles.Selectable,true);TabStop=true;BackColor=Color.FromArgb(20,23,27);Dock=DockStyle.Fill;AllowDrop=true;}
        public void Bind(Workspace w,UiDocument d){Workspace=w;Document=d;AtlasFile=d==null?"":d.DefaultAtlasReference;Selection.Clear();Options.Aspect=d!=null&&!d.Atlas&&System.IO.Path.GetFileNameWithoutExtension(d.FilePath).EndsWith("_16",StringComparison.OrdinalIgnoreCase)?4f/3f:1;Fit();ChangedSelection();}
        public float Aspect {get{return Document!=null&&Document.Atlas?1:Options.Aspect;}}
        public PointF ToWorld(Point p){return new PointF((p.X-Pan.X)/(Zoom*Aspect),(p.Y-Pan.Y)/Zoom);}
        public PointF ToScreen(PointF p){return new PointF(p.X*Zoom*Aspect+Pan.X,p.Y*Zoom+Pan.Y);}
        public RectangleF ScreenRect(RectangleF r){var p=ToScreen(r.Location);return new RectangleF(p.X,p.Y,r.Width*Zoom*Aspect,r.Height*Zoom);}
        public UiNode Primary {get{return Document==null||Selection.Count==0?null:Document.Node(Selection[0]);}}
        public RectangleF Frame(){if(Document!=null&&Document.Atlas){try{var path=Workspace.ResolveFile(AtlasFile);var b=Workspace.Image(path);if(b!=null)return new RectangleF(0,0,b.Width,b.Height);}catch(Exception){}}return new RectangleF(0,0,1024,768);}
        public void Fit(){RectangleF r=Frame();FitRect(r);}
        public void FitSelection(){var n=Primary;if(n!=null)FitRect(UiLayout.Rect(Document,n));else Fit();}
        void FitRect(RectangleF r){if(ClientSize.Width<50||ClientSize.Height<50||r.Width<=0||r.Height<=0)return;Zoom=Math.Max(.04f,Math.Min(8,Math.Min((ClientSize.Width-60)/(r.Width*Aspect),(ClientSize.Height-60)/r.Height)));Pan=new PointF((ClientSize.Width-r.Width*Zoom*Aspect)/2-r.X*Zoom*Aspect,(ClientSize.Height-r.Height*Zoom)/2-r.Y*Zoom);Invalidate();Report("Масштаб: "+Math.Round(Zoom*100)+"%");}
        public void SetZoom(float zoom){ZoomAt(zoom,new Point(ClientSize.Width/2,ClientSize.Height/2));}
        void ZoomAt(float zoom,Point p){PointF w=ToWorld(p);Zoom=Math.Max(.04f,Math.Min(16,zoom));Pan=new PointF(p.X-w.X*Zoom*Aspect,p.Y-w.Y*Zoom);Invalidate();Report("Масштаб: "+Math.Round(Zoom*100)+"%");}
        public void SelectKey(string key,bool additive){if(!additive)Selection.Clear();if(key!=null&&!Selection.Contains(key))Selection.Add(key);if(Document!=null&&Document.Atlas&&Primary!=null){string page=Document.AtlasReference(Primary);if(page!="")AtlasFile=page;}ChangedSelection();}
        void ChangedSelection(){Invalidate();if(SelectionChanged!=null)SelectionChanged(this,EventArgs.Empty);}
        void Report(string text){if(StatusChanged!=null)StatusChanged(text);}
        void Error(Exception ex){if(Failure!=null)Failure(ex.Message);}
        protected override void OnPaint(PaintEventArgs e){base.OnPaint(e);try{Draw(e.Graphics,ClientRectangle,true);}catch(Exception ex){TextRenderer.DrawText(e.Graphics,"Ошибка просмотра: "+ex.Message,Font,new Rectangle(20,50,Math.Max(20,Width-40),100),Color.Salmon,TextFormatFlags.WordBreak);}}
        void Draw(Graphics g,Rectangle viewport,bool editing){
            g.Clear(Options.BackgroundColor);if(Document==null){TextRenderer.DrawText(g,"Откройте папку gamedata или UI XML\nCtrl+O — открыть XML     Ctrl+Shift+O — открыть проект",Font,new Rectangle(30,80,Math.Max(100,Width-60),100),Color.FromArgb(185,190,196),TextFormatFlags.HorizontalCenter|TextFormatFlags.WordBreak);return;}
            g.SmoothingMode=SmoothingMode.None;g.InterpolationMode=Zoom>=1?InterpolationMode.NearestNeighbor:InterpolationMode.HighQualityBilinear;g.PixelOffsetMode=PixelOffsetMode.Half;
            RectangleF frame=ScreenRect(Frame());if(Options.Checker){using(var a=new SolidBrush(Color.FromArgb(31,35,41)))using(var b=new SolidBrush(Color.FromArgb(38,42,48))){g.FillRectangle(a,frame);int tile=16;Rectangle clip=Rectangle.Intersect(Rectangle.Ceiling(frame),viewport);for(int y=clip.Top/tile*tile;y<clip.Bottom;y+=tile)for(int x=clip.Left/tile*tile;x<clip.Right;x+=tile)if(((x/tile+y/tile)&1)==0)g.FillRectangle(b,Rectangle.Intersect(new Rectangle(x,y,tile,tile),clip));}}
            if(Options.Background){if(Document.Atlas){string path=Workspace.ResolveFile(AtlasFile);DrawTexture(g,path,Frame(),Frame());}
                else if(!string.IsNullOrEmpty(Options.ManualBackground)){var image=Workspace.Image(Options.ManualBackground);DrawTexture(g,Options.ManualBackground,new RectangleF(0,0,image.Width,image.Height),Frame());}
                else foreach(var n in VisibleNodes()){string name=UiLayout.TextureName(Document,n);if(name=="")continue;try{var t=Workspace.Resolve(name);if(t!=null)DrawNodeTexture(g,n,t);}catch(Exception){}}
            }
            if(Options.Grid)DrawGrid(g,viewport);
            using(var border=new Pen(Color.FromArgb(80,170,180,190),1))g.DrawRectangle(border,frame.X,frame.Y,frame.Width,frame.Height);
            foreach(var n in VisibleNodes()){
                RectangleF r=ScreenRect(UiLayout.Rect(Document,n));if(r.Right<0||r.Bottom<0||r.Left>viewport.Right||r.Top>viewport.Bottom)continue;
                bool selected=Selection.Contains(n.Key);Color color=NodeColor(n);if(Document.Locked.Contains(n.Key))color=Color.FromArgb(117,125,134);
                if(Options.Outlines||selected){using(var pen=new Pen(Color.FromArgb(selected?255:130,color),selected?2:1)){if(Document.Locked.Contains(n.Key))pen.DashStyle=DashStyle.Dot;g.DrawRectangle(pen,r.X,r.Y,r.Width,r.Height);}}
                if(Options.Cells&&n.Has("cell_width")&&n.Has("cell_height")){int cols=Math.Min(200,(int)n.Number("cols_num",1)),rows=Math.Min(200,(int)n.Number("rows_num",1));float cw=n.Number("cell_width",1)*Zoom*Aspect,ch=n.Number("cell_height",1)*Zoom;if(cw>3&&ch>3)using(var pen=new Pen(Color.FromArgb(105,color),1)){for(int c=1;c<cols;c++){float x=r.X+c*cw;if(x>=r.Right)break;g.DrawLine(pen,x,r.Top,x,r.Bottom);}for(int row=1;row<rows;row++){float y=r.Y+row*ch;if(y>=r.Bottom)break;g.DrawLine(pen,r.Left,y,r.Right,y);}}}
                if((Options.Names||selected)&&r.Width>26&&r.Height>12){string label=Document.Atlas?n.Get("id",n.Name):n.Name;string tx=UiLayout.TextureName(Document,n);if(selected&&!Document.Atlas&&tx!="")label+="  ·  "+tx;int labelWidth=(int)Math.Min(Math.Max(0,viewport.Right-r.Left-4),Math.Max(60,r.Width));Rectangle labelRect=new Rectangle((int)r.Left+2,(int)r.Top+2,labelWidth,17);using(var brush=new SolidBrush(Color.FromArgb(210,21,24,29)))g.FillRectangle(brush,labelRect);TextRenderer.DrawText(g,label,Font,labelRect,selected?Color.FromArgb(251,216,151):color,TextFormatFlags.EndEllipsis|TextFormatFlags.NoPrefix|TextFormatFlags.SingleLine);}
            }
            if(editing&&Selection.Count==1&&Primary!=null&&Primary.Geometry&&!Document.Locked.Contains(Primary.Key)){foreach(var r in Handles(ScreenRect(UiLayout.Rect(Document,Primary)))){g.FillRectangle(Brushes.White,r);g.DrawRectangle(Pens.Black,r.X,r.Y,r.Width,r.Height);}}
            if(Options.Rulers&&editing)DrawRulers(g,viewport);
        }
        List<UiNode> VisibleNodes(){var nodes=UiLayout.Visible(Document);if(Document.Atlas)nodes.RemoveAll(delegate(UiNode n){return Document.AtlasReference(n)!=AtlasFile;});return nodes;}
        void DrawNodeTexture(Graphics g,UiNode n,TextureRegion t){var tx=n.Child("texture")??n.Child("texture_e");RectangleF source=t.Source;if(tx!=null){source.X+=tx.Number("x",0);source.Y+=tx.Number("y",0);source.Width=tx.Number("width",source.Width);source.Height=tx.Number("height",source.Height);}if(t.FilePath==null||source.Width<=0||source.Height<=0)return;var world=UiLayout.Rect(Document,n);var dest=ScreenRect(world);Bitmap image=Workspace.Image(t.FilePath);string mirror=tx==null?"":tx.Get("mirror","");if(mirror=="h"||mirror=="v"){PointF[] points=mirror=="h"?new[]{new PointF(dest.Right,dest.Top),new PointF(dest.Left,dest.Top),new PointF(dest.Right,dest.Bottom)}:new[]{new PointF(dest.Left,dest.Bottom),new PointF(dest.Right,dest.Bottom),new PointF(dest.Left,dest.Top)};g.DrawImage(image,points,source,GraphicsUnit.Pixel);}else DrawTexture(g,t.FilePath,source,world);}
        bool SelectedAncestor(UiNode n){var p=UiLayout.Parent(Document,n);int guard=0;while(p!=null&&guard++<40){if(Selection.Contains(p.Key))return true;p=UiLayout.Parent(Document,p);}return false;}
        void DrawTexture(Graphics g,string path,RectangleF source,RectangleF world){if(path==null||source.Width<=0||source.Height<=0||world.Width<=0||world.Height<=0)return;Bitmap image=Workspace.Image(path);if(image==null)return;RectangleF dest=ScreenRect(world);g.DrawImage(image,dest,source,GraphicsUnit.Pixel);}
        static Color NodeColor(UiNode n){if(n.Name.StartsWith("dragdrop_"))return Color.FromArgb(231,190,113);if(n.Name=="texture")return Color.FromArgb(125,211,205);if(n.Name.Contains("progress"))return Color.FromArgb(151,206,151);if(n.Name.Contains("back"))return Color.FromArgb(123,163,210);return Color.FromArgb(172,167,202);}
        void DrawGrid(Graphics g,Rectangle viewport){float sx=Math.Max(1,Options.GridX),sy=Math.Max(1,Options.GridY);while(sx*Zoom*Aspect<7)sx*=2;while(sy*Zoom<7)sy*=2;PointF a=ToWorld(new Point(0,0)),b=ToWorld(new Point(viewport.Right,viewport.Bottom));int major=Math.Max(1,Options.Major);using(var minor=new Pen(Color.FromArgb(38,Options.GridColor)))using(var bold=new Pen(Color.FromArgb(85,Options.GridColor))){int i0=(int)Math.Floor(a.X/sx),i1=(int)Math.Ceiling(b.X/sx);for(int i=i0;i<=i1&&i-i0<2000;i++){float x=ToScreen(new PointF(i*sx,0)).X;g.DrawLine(i%major==0?bold:minor,x,0,x,viewport.Bottom);}int j0=(int)Math.Floor(a.Y/sy),j1=(int)Math.Ceiling(b.Y/sy);for(int j=j0;j<=j1&&j-j0<2000;j++){float y=ToScreen(new PointF(0,j*sy)).Y;g.DrawLine(j%major==0?bold:minor,0,y,viewport.Right,y);}}}
        void DrawRulers(Graphics g,Rectangle viewport){using(var brush=new SolidBrush(Color.FromArgb(235,28,32,38))){g.FillRectangle(brush,0,0,viewport.Width,20);g.FillRectangle(brush,0,20,28,viewport.Height);}float step=32;while(step*Zoom*Aspect<54)step*=2;PointF min=ToWorld(new Point(28,20)),max=ToWorld(new Point(viewport.Right,viewport.Bottom));using(var rulerFont=new Font(Font.FontFamily,7))using(var pen=new Pen(Color.FromArgb(115,127,140))){for(float x=(float)Math.Ceiling(min.X/step)*step;x<max.X;x+=step){float px=ToScreen(new PointF(x,0)).X;g.DrawLine(pen,px,15,px,20);TextRenderer.DrawText(g,UiDocument.Num(x),Font,new Point((int)px+3,2),Color.Silver);}while(step*Zoom<40)step*=2;for(float y=(float)Math.Ceiling(min.Y/step)*step;y<max.Y;y+=step){float py=ToScreen(new PointF(0,y)).Y;g.DrawLine(pen,23,py,28,py);TextRenderer.DrawText(g,UiDocument.Num(y),rulerFont,new Rectangle(0,(int)py-8,25,16),Color.Silver,TextFormatFlags.Right);}}}
        static RectangleF[] Handles(RectangleF r){float x=r.X,y=r.Y,w=r.Width,h=r.Height;PointF[] p={new PointF(x,y),new PointF(x+w/2,y),new PointF(x+w,y),new PointF(x+w,y+h/2),new PointF(x+w,y+h),new PointF(x+w/2,y+h),new PointF(x,y+h),new PointF(x,y+h/2)};var result=new RectangleF[8];for(int i=0;i<8;i++)result[i]=new RectangleF(p[i].X-4,p[i].Y-4,8,8);return result;}
        UiNode Hit(PointF p){if(Document==null)return null;var nodes=VisibleNodes();UiNode hit=null;float area=float.MaxValue;for(int i=nodes.Count-1;i>=0;i--){var n=nodes[i];var r=UiLayout.Rect(Document,n);if(!Document.Locked.Contains(n.Key)&&r.Contains(p)&&r.Width*r.Height<area){hit=n;area=r.Width*r.Height;}}return hit;}
        protected override void OnMouseWheel(MouseEventArgs e){base.OnMouseWheel(e);ZoomAt(Zoom*(e.Delta>0?1.15f:1/1.15f),e.Location);}
        protected override void OnMouseDown(MouseEventArgs e){base.OnMouseDown(e);Focus();if(e.Button==MouseButtons.Middle||space&&e.Button==MouseButtons.Left){panning=true;mouseStart=e.Location;panStart=Pan;Capture=true;Cursor=Cursors.Hand;return;}if(e.Button!=MouseButtons.Left||Document==null)return;
            resizeHandle=-1;var primary=Primary;if(Selection.Count==1&&primary!=null&&!Document.Locked.Contains(primary.Key)){var handles=Handles(ScreenRect(UiLayout.Rect(Document,primary)));for(int i=0;i<8;i++)if(handles[i].Contains(e.Location)){resizeHandle=i;break;}}
            if(resizeHandle<0){var hit=Hit(ToWorld(e.Location));bool ctrl=(ModifierKeys&Keys.Control)!=0;if(hit==null){if(!ctrl)Selection.Clear();ChangedSelection();return;}if(ctrl){if(Selection.Contains(hit.Key))Selection.Remove(hit.Key);else Selection.Add(hit.Key);ChangedSelection();return;}if(!Selection.Contains(hit.Key)){Selection.Clear();Selection.Add(hit.Key);ChangedSelection();}}
            before=Document.Text;mouseStart=e.Location;worldStart=ToWorld(e.Location);initial.Clear();foreach(string key in Selection){var n=Document.Node(key);if(n!=null&&!Document.Locked.Contains(key)&&n.Geometry&&!SelectedAncestor(n))initial[key]=n.LocalRect;}dragging=initial.Count>0;moved=false;Capture=dragging;
        }
        protected override void OnMouseMove(MouseEventArgs e){base.OnMouseMove(e);if(panning){Pan=new PointF(panStart.X+e.X-mouseStart.X,panStart.Y+e.Y-mouseStart.Y);Invalidate();return;}PointF world=ToWorld(e.Location);
            if(dragging){if(!moved&&Math.Abs(e.X-mouseStart.X)+Math.Abs(e.Y-mouseStart.Y)<3)return;moved=true;float dx=world.X-worldStart.X,dy=world.Y-worldStart.Y;if((ModifierKeys&Keys.Shift)!=0&&resizeHandle<0){if(Math.Abs(dx)>Math.Abs(dy))dy=0;else dx=0;}
                bool snap=Options.Snap&&(ModifierKeys&Keys.Alt)==0;if(snap&&resizeHandle<0&&initial.Count>0){foreach(var pair in initial){dx=Snap(pair.Value.X+dx,Options.GridX)-pair.Value.X;dy=Snap(pair.Value.Y+dy,Options.GridY)-pair.Value.Y;break;}}var changes=new Dictionary<string,Dictionary<string,string>>();
                foreach(var pair in initial){RectangleF start=pair.Value,r=start;float nx=dx,ny=dy;
                    if(resizeHandle<0){r.X+=nx;r.Y+=ny;}
                    else{float left=start.Left,top=start.Top,right=start.Right,bottom=start.Bottom;if(resizeHandle==0||resizeHandle==6||resizeHandle==7)left=snap?Snap(start.Left+dx,Options.GridX):start.Left+dx;if(resizeHandle==0||resizeHandle==1||resizeHandle==2)top=snap?Snap(start.Top+dy,Options.GridY):start.Top+dy;if(resizeHandle==2||resizeHandle==3||resizeHandle==4)right=snap?Snap(start.Right+dx,Options.GridX):start.Right+dx;if(resizeHandle==4||resizeHandle==5||resizeHandle==6)bottom=snap?Snap(start.Bottom+dy,Options.GridY):start.Bottom+dy;left=Math.Min(left,right-1);top=Math.Min(top,bottom-1);r=RectangleF.FromLTRB(left,top,right,bottom);}
                    var values=new Dictionary<string,string>();values["x"]=UiDocument.Num(r.X);values["y"]=UiDocument.Num(r.Y);if(resizeHandle>=0){values["width"]=UiDocument.Num(r.Width);values["height"]=UiDocument.Num(r.Height);}changes[pair.Key]=values;
                }
                try{Document.SetAttributes(changes);Invalidate();if(GeometryPreview!=null)GeometryPreview(this,EventArgs.Empty);}catch(Exception ex){Error(ex);CancelDrag();}return;
            }
            string status="X: "+UiDocument.Num(world.X)+"   Y: "+UiDocument.Num(world.Y)+"   Масштаб: "+Math.Round(Zoom*100)+"%";UiNode hovered=Hit(world);if(hovered!=null){string tex=UiLayout.TextureName(Document,hovered);status+="   <"+hovered.Name+">"+(tex==""?"":"   Текстура: "+tex);if(hover!=hovered.Key){hover=hovered.Key;tooltip.SetToolTip(this,"<"+hovered.Name+">\n"+hovered.Key+"\nТекстура: "+(tex==""?"—":tex)+"\nCtrl+клик: несколько элементов · Alt: без привязки");}}else if(hover!=""){hover="";tooltip.SetToolTip(this,"");}Report(status);
        }
        protected override void OnMouseUp(MouseEventArgs e){base.OnMouseUp(e);if(panning){panning=false;Capture=false;Cursor=Cursors.Default;return;}if(dragging){dragging=false;Capture=false;if(moved){Document.Commit(before);if(EditCommitted!=null)EditCommitted(this,EventArgs.Empty);}Invalidate();}}
        void CancelDrag(){if(dragging&&before!=null)Document.SetText(before);dragging=false;panning=false;Capture=false;Invalidate();if(EditCommitted!=null)EditCommitted(this,EventArgs.Empty);}
        static float Snap(float n,int step){return (float)Math.Round(n/Math.Max(1,step))*Math.Max(1,step);}
        public void MoveSelected(float dx,float dy){if(Document==null)return;string old=Document.Text;var changes=new Dictionary<string,Dictionary<string,string>>();foreach(string key in Selection){var n=Document.Node(key);if(n==null||!n.Geometry||Document.Locked.Contains(key)||SelectedAncestor(n))continue;changes[key]=new Dictionary<string,string>{{"x",UiDocument.Num(n.Number("x",0)+dx)},{"y",UiDocument.Num(n.Number("y",0)+dy)}};}Document.SetAttributes(changes);Document.Commit(old);if(EditCommitted!=null)EditCommitted(this,EventArgs.Empty);Invalidate();}
        public void Align(string mode){if(Document==null||Selection.Count<2)return;string beforeText=Document.Text;var changes=new Dictionary<string,Dictionary<string,string>>();RectangleF anchor=UiLayout.Rect(Document,Primary);
            foreach(string key in Selection){var n=Document.Node(key);if(n==null||!n.Geometry||Document.Locked.Contains(key)||SelectedAncestor(n))continue;var r=UiLayout.Rect(Document,n);float dx=mode=="left"?anchor.Left-r.Left:mode=="centerx"?anchor.Left+anchor.Width/2-r.Left-r.Width/2:0;float dy=mode=="top"?anchor.Top-r.Top:mode=="centery"?anchor.Top+anchor.Height/2-r.Top-r.Height/2:0;changes[key]=new Dictionary<string,string>{{"x",UiDocument.Num(n.Number("x",0)+dx)},{"y",UiDocument.Num(n.Number("y",0)+dy)}};}
            Document.SetAttributes(changes);Document.Commit(beforeText);if(EditCommitted!=null)EditCommitted(this,EventArgs.Empty);Invalidate();}
        public void Export(string path){RectangleF f=Frame();int width=(int)Math.Ceiling(f.Width*Aspect),height=(int)Math.Ceiling(f.Height);if(width>8192||height>8192)throw new InvalidOperationException("Слишком большой экспорт.");float z=Zoom;PointF pan=Pan;try{Zoom=1;Pan=PointF.Empty;using(var b=new Bitmap(width,height))using(var g=Graphics.FromImage(b)){Draw(g,new Rectangle(0,0,width,height),false);b.Save(path,ImageFormat.Png);}}finally{Zoom=z;Pan=pan;}}
        protected override bool IsInputKey(Keys keyData){if((keyData&Keys.KeyCode)==Keys.Left||(keyData&Keys.KeyCode)==Keys.Right||(keyData&Keys.KeyCode)==Keys.Up||(keyData&Keys.KeyCode)==Keys.Down)return true;return base.IsInputKey(keyData);}
        protected override void OnKeyDown(KeyEventArgs e){base.OnKeyDown(e);if(e.KeyCode==Keys.Space){space=true;e.Handled=true;}if(e.KeyCode==Keys.Escape){CancelDrag();e.Handled=true;}float step=e.Shift?10:1;if(e.KeyCode==Keys.Left){MoveSelected(-step,0);e.Handled=true;}if(e.KeyCode==Keys.Right){MoveSelected(step,0);e.Handled=true;}if(e.KeyCode==Keys.Up){MoveSelected(0,-step);e.Handled=true;}if(e.KeyCode==Keys.Down){MoveSelected(0,step);e.Handled=true;}if(e.KeyCode==Keys.F){FitSelection();e.Handled=true;}}
        protected override void OnKeyUp(KeyEventArgs e){base.OnKeyUp(e);if(e.KeyCode==Keys.Space)space=false;}
        protected override void OnLostFocus(EventArgs e){base.OnLostFocus(e);space=false;}
        protected override void Dispose(bool disposing){if(disposing)tooltip.Dispose();base.Dispose(disposing);}
    }
}
