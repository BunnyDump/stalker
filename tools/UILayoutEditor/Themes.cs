using System;using System.Collections.Generic;using System.Drawing;using System.Windows.Forms;
namespace HalkUIEditor {
    public sealed class ThemePalette {
        public string Id,Name,Detail; public Color Background,Panel,Raised,Input,Text,Muted,Accent,Selection,Border,Canvas,Grid,Geometry; public bool Light;
        public override string ToString(){return Name;}
        public Color SelectedText {get{return Light?Text:Color.White;}}
    }
    public static class ThemeCatalog {
        public static readonly string[] Ids={"classic","system","dark","light","soc","cs","cop"};
        static Color C(int rgb){return Color.FromArgb((rgb>>16)&255,(rgb>>8)&255,rgb&255);}
        public static ThemePalette Create(string id){
            var p=new ThemePalette{Id=id,Name="Текущая",Detail="Графит и янтарь",Background=C(0x191d23),Panel=C(0x262a31),Raised=C(0x343a43),Input=C(0x1b1f25),Text=C(0xe4e8ee),Muted=C(0xa7b2bf),Accent=C(0xe8bf78),Selection=C(0x554936),Border=C(0x424c59),Canvas=C(0x14171b),Grid=C(0x6e95a5),Geometry=C(0x93cbc6)};
            switch(id){
                case "system":p.Name="Системная";p.Detail="Цвета и контраст Windows";p.Background=SystemColors.ControlDark;p.Panel=SystemColors.Control;p.Raised=SystemColors.ControlLight;p.Input=SystemColors.Window;p.Text=SystemColors.ControlText;p.Muted=SystemColors.GrayText;p.Accent=SystemColors.Highlight;p.Selection=SystemColors.Highlight;p.Border=SystemColors.ControlDark;p.Canvas=SystemColors.AppWorkspace;p.Grid=SystemColors.ControlText;p.Geometry=SystemColors.ControlText;p.Light=p.Panel.GetBrightness()>.5f;break;
                case "dark":p.Name="Тёмная";p.Detail="Уголь и холодный голубой";p.Background=C(0x101317);p.Panel=C(0x1b2027);p.Raised=C(0x29313c);p.Input=C(0x12171d);p.Accent=C(0x78b9ec);p.Selection=C(0x263f55);p.Border=C(0x35414f);p.Canvas=C(0x0d1116);p.Grid=C(0x659ac1);break;
                case "light":p.Name="Светлая";p.Detail="Светлая рабочая поверхность";p.Background=C(0xdfe5eb);p.Panel=C(0xf1f4f7);p.Raised=C(0xe4eaf0);p.Input=C(0xffffff);p.Text=C(0x23313e);p.Muted=C(0x536576);p.Accent=C(0x90601f);p.Selection=C(0xe8dac2);p.Border=C(0xb9c4d0);p.Canvas=C(0xe8edf2);p.Grid=C(0x607c94);p.Geometry=C(0x296e65);p.Light=true;break;
                case "soc":p.Name="S.T.A.L.K.E.R. ТЧ";p.Detail="Тень Чернобыля · олива, пыль и янтарь";p.Background=C(0x1a1b14);p.Panel=C(0x2b2d22);p.Raised=C(0x3b3d2e);p.Input=C(0x1e2118);p.Text=C(0xe3dbc3);p.Muted=C(0xb3b095);p.Accent=C(0xdfb566);p.Selection=C(0x55492d);p.Border=C(0x595a40);p.Canvas=C(0x15170f);p.Grid=C(0x8c9269);p.Geometry=C(0xa7c088);break;
                case "cs":p.Name="S.T.A.L.K.E.R. ЧН";p.Detail="Чистое Небо · холодная сталь и бирюза";p.Background=C(0x111b22);p.Panel=C(0x21303b);p.Raised=C(0x30434f);p.Input=C(0x16232c);p.Text=C(0xdce8ee);p.Muted=C(0xa2b8c5);p.Accent=C(0x88ccd6);p.Selection=C(0x315260);p.Border=C(0x466472);p.Canvas=C(0x0e191f);p.Grid=C(0x739aa8);p.Geometry=C(0x97c4d3);break;
                case "cop":p.Name="S.T.A.L.K.E.R. ЗП";p.Detail="Зов Припяти · зелёный экран полевого КПК";p.Background=C(0x121a16);p.Panel=C(0x243127);p.Raised=C(0x34463a);p.Input=C(0x17241c);p.Text=C(0xdbe3cb);p.Muted=C(0xa5b99b);p.Accent=C(0xb7cf78);p.Selection=C(0x465a35);p.Border=C(0x4e6451);p.Canvas=C(0x101911);p.Grid=C(0x72976a);p.Geometry=C(0x98c599);break;
                default:p.Id="classic";break;
            }return p;
        }
        public static Color SelectionText(ThemePalette p){return p.Id=="system"?SystemColors.HighlightText:p.SelectedText;}
        public static void Apply(Control c,ThemePalette p){
            if(c is EditorCanvas){((EditorCanvas)c).Palette=p;c.Invalidate();return;}
            c.ForeColor=p.Text;c.BackColor=c is TextBoxBase||c is ListBox||c is TreeView||c is NumericUpDown||c is ComboBox?p.Input:p.Panel;
            var tabs=c as ThemeTabs;if(tabs!=null){tabs.Palette=p;tabs.Invalidate();}
            var preview=c as TexturePreview;if(preview!=null){preview.Palette=p;preview.Invalidate();}
            var grid=c as DataGridView;if(grid!=null){grid.BackgroundColor=p.Input;grid.GridColor=p.Border;grid.EnableHeadersVisualStyles=false;grid.ColumnHeadersDefaultCellStyle.BackColor=p.Raised;grid.ColumnHeadersDefaultCellStyle.ForeColor=p.Muted;grid.ColumnHeadersDefaultCellStyle.SelectionBackColor=p.Raised;grid.ColumnHeadersDefaultCellStyle.SelectionForeColor=p.Text;grid.DefaultCellStyle.BackColor=p.Input;grid.DefaultCellStyle.ForeColor=p.Text;grid.DefaultCellStyle.SelectionBackColor=p.Selection;grid.DefaultCellStyle.SelectionForeColor=SelectionText(p);grid.AlternatingRowsDefaultCellStyle.BackColor=p.Panel;grid.CellBorderStyle=DataGridViewCellBorderStyle.SingleHorizontal;grid.ColumnHeadersBorderStyle=DataGridViewHeaderBorderStyle.None;}
            var button=c as Button;if(button!=null){button.BackColor=p.Raised;button.FlatAppearance.BorderColor=p.Border;button.FlatAppearance.MouseOverBackColor=p.Selection;button.FlatAppearance.MouseDownBackColor=p.Selection;}
            var strip=c as ToolStrip;if(strip!=null){strip.Renderer=new ThemeRenderer(p);foreach(ToolStripItem item in strip.Items)ApplyItem(item,p);}
            foreach(Control child in c.Controls)Apply(child,p);if(c.Tag as string=="muted")c.ForeColor=p.Muted;else if(c.Tag as string=="heading")c.ForeColor=p.Accent;
        }
        static void ApplyItem(ToolStripItem item,ThemePalette p){item.BackColor=p.Panel;item.ForeColor=p.Text;var host=item as ToolStripControlHost;if(host!=null)Apply(host.Control,p);var menu=item as ToolStripDropDownItem;if(menu!=null){menu.DropDown.BackColor=p.Panel;menu.DropDown.ForeColor=p.Text;menu.DropDown.Renderer=new ThemeRenderer(p);foreach(ToolStripItem child in menu.DropDownItems)ApplyItem(child,p);}}
    }
    public sealed class ThemeTabs : TabControl {
        public ThemePalette Palette=ThemeCatalog.Create("classic");
        public ThemeTabs(){SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);SizeMode=TabSizeMode.Fixed;ItemSize=new Size(82,30);Padding=new Point(10,5);}
        protected override void OnPaint(PaintEventArgs e){var p=Palette;var g=e.Graphics;g.Clear(p.Panel);using(var border=new Pen(p.Border))g.DrawLine(border,0,31,Width,31);for(int i=0;i<TabPages.Count;i++){var r=GetTabRect(i);bool selected=i==SelectedIndex;using(var br=new SolidBrush(selected?p.Input:p.Panel))g.FillRectangle(br,r);if(selected)using(var br=new SolidBrush(p.Accent))g.FillRectangle(br,r.X+8,r.Bottom-3,r.Width-16,2);TextRenderer.DrawText(g,TabPages[i].Text,Font,r,selected?p.Text:p.Muted,TextFormatFlags.HorizontalCenter|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis|TextFormatFlags.NoPrefix);}}
        void FitHeaders(){if(TabPages.Count==0)return;int width=Math.Min(110,Math.Max(36,(ClientSize.Width-10)/TabPages.Count));if(ItemSize.Width!=width)ItemSize=new Size(width,30);}
        protected override void OnSizeChanged(EventArgs e){base.OnSizeChanged(e);FitHeaders();Invalidate();}
        protected override void OnControlAdded(ControlEventArgs e){base.OnControlAdded(e);FitHeaders();}
        protected override void OnSelectedIndexChanged(EventArgs e){base.OnSelectedIndexChanged(e);FitHeaders();Invalidate();}
    }
    sealed class ThemeRenderer : ToolStripProfessionalRenderer {
        readonly ThemePalette palette;
        public ThemeRenderer(ThemePalette p):base(new ThemeColors(p)){palette=p;RoundedEdges=false;}
        protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e){using(var br=new SolidBrush(palette.Panel))e.Graphics.FillRectangle(br,e.AffectedBounds);}
        protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e){using(var pen=new Pen(palette.Border))e.Graphics.DrawLine(pen,0,e.ToolStrip.Height-1,e.ToolStrip.Width,e.ToolStrip.Height-1);}
        protected override void OnRenderButtonBackground(ToolStripItemRenderEventArgs e){var b=e.Item as ToolStripButton;bool active=b!=null&&b.Checked;using(var br=new SolidBrush(e.Item.Pressed||e.Item.Selected||active?palette.Selection:palette.Panel))e.Graphics.FillRectangle(br,new Rectangle(Point.Empty,e.Item.Size));if(active)using(var br=new SolidBrush(palette.Accent))e.Graphics.FillRectangle(br,5,e.Item.Height-3,Math.Max(1,e.Item.Width-10),2);}
        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e){e.TextColor=!e.Item.Enabled?palette.Muted:(e.Item.Selected||e.Item is ToolStripButton&&((ToolStripButton)e.Item).Checked)&&palette.Id=="system"?SystemColors.HighlightText:palette.Text;base.OnRenderItemText(e);}
    }
    sealed class ThemeColors : ProfessionalColorTable {
        readonly ThemePalette p;public ThemeColors(ThemePalette palette){p=palette;UseSystemColors=false;}
        public override Color ToolStripGradientBegin{get{return p.Panel;}}public override Color ToolStripGradientMiddle{get{return p.Panel;}}public override Color ToolStripGradientEnd{get{return p.Panel;}}public override Color ToolStripDropDownBackground{get{return p.Panel;}}public override Color MenuStripGradientBegin{get{return p.Panel;}}public override Color MenuStripGradientEnd{get{return p.Panel;}}public override Color ImageMarginGradientBegin{get{return p.Panel;}}public override Color ImageMarginGradientMiddle{get{return p.Panel;}}public override Color ImageMarginGradientEnd{get{return p.Panel;}}public override Color MenuItemSelected{get{return p.Selection;}}public override Color MenuItemSelectedGradientBegin{get{return p.Selection;}}public override Color MenuItemSelectedGradientEnd{get{return p.Selection;}}public override Color MenuItemPressedGradientBegin{get{return p.Selection;}}public override Color MenuItemPressedGradientMiddle{get{return p.Selection;}}public override Color MenuItemPressedGradientEnd{get{return p.Selection;}}public override Color MenuBorder{get{return p.Border;}}public override Color MenuItemBorder{get{return p.Border;}}public override Color ButtonSelectedBorder{get{return p.Accent;}}public override Color ButtonCheckedGradientBegin{get{return p.Selection;}}public override Color ButtonCheckedGradientMiddle{get{return p.Selection;}}public override Color ButtonCheckedGradientEnd{get{return p.Selection;}}public override Color SeparatorDark{get{return p.Border;}}public override Color SeparatorLight{get{return p.Panel;}}
    }
}
