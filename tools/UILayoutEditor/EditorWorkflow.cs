using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Windows.Forms;

namespace HalkUIEditor {
    public static class XmlSearch {
        public static int Find(string text, string query, int start, bool backwards, bool matchCase) {
            if (string.IsNullOrEmpty(query) || query.Length > text.Length) return -1;
            StringComparison comparison = matchCase ? StringComparison.Ordinal : StringComparison.OrdinalIgnoreCase;
            if (backwards) {
                int lastStart = text.Length - query.Length;
                int limit = Math.Min(start, lastStart);
                int found = limit < 0 ? -1 : text.LastIndexOf(query, limit + query.Length - 1, limit + query.Length, comparison);
                return found >= 0 ? found : text.LastIndexOf(query, comparison);
            }
            int next = text.IndexOf(query, Math.Max(0, Math.Min(text.Length, start)), comparison);
            return next >= 0 ? next : text.IndexOf(query, comparison);
        }
    }

    sealed class TreeState {
        public HashSet<string> Expanded = new HashSet<string>();
        public string Top;
    }
    sealed class DocumentView {
        public float Zoom;
        public PointF Pan;
        public int Aspect, Tab, Caret;
        public string Atlas, Filter;
        public TreeState Tree;
        public List<string> Selection;
    }

    public sealed partial class MainForm {
        readonly Dictionary<string, DocumentView> documentViews = new Dictionary<string, DocumentView>(StringComparer.OrdinalIgnoreCase);
        readonly Stack<string> backHistory = new Stack<string>(), forwardHistory = new Stack<string>();
        readonly Timer filterTimer = new Timer { Interval = 180 };
        bool pendingFiles, pendingNodes, pendingTextures, pendingFind;
        UiDocument treeDocument;
        string treeQuery = "";
        ToolStripButton backButton, forwardButton, atlasButton, xmlButton;
        ToolStripLabel selectionCount = new ToolStripLabel();
        ToolStripDropDownButton arrangeButton;
        readonly ContextMenuStrip canvasMenu = new ContextMenuStrip();
        ToolStrip findStrip;
        ToolStripTextBox findText = new ToolStripTextBox();
        ToolStripLabel findCount = new ToolStripLabel();
        ToolStripButton findCase = new ToolStripButton("Aa") { CheckOnClick = true, ToolTipText = "Учитывать регистр" };
        SourceGutter sourceGutter;
        bool sourceHistoryActive;

        void FitWindowToDisplay() {
            Rectangle work = Screen.FromControl(this).WorkingArea;
            Size = new Size(Math.Min(Width, work.Width), Math.Min(Height, work.Height));
            Location = new Point(Math.Max(work.Left, Math.Min(Left, work.Right - Width)), Math.Max(work.Top, Math.Min(Top, work.Bottom - Height)));
        }

        void InitializeWorkflow() {
            var viewMenu = (ToolStripMenuItem)MainMenuStrip.Items[2];
            AddMenu(viewMenu, "Назад к предыдущему XML", Keys.Alt | Keys.Left, delegate { NavigateHistory(true); });
            AddMenu(viewMenu, "Вперёд к следующему XML", Keys.Alt | Keys.Right, delegate { NavigateHistory(false); });
            var editMenu = (ToolStripMenuItem)MainMenuStrip.Items[1];
            editMenu.DropDownItems.Add(new ToolStripSeparator());
            AddMenu(editMenu, "Найти в XML…", Keys.Control | Keys.F, ShowFind);
            AddMenu(editMenu, "Следующее совпадение", Keys.F3, delegate { FindSource(false); });
            AddMenu(editMenu, "Предыдущее совпадение", Keys.Shift | Keys.F3, delegate { FindSource(true); });
            foreach (Control control in Controls) {
                var strip = control as ToolStrip;
                if (strip == null || strip.Items.Count == 0 || strip.Items[0].Text != "Открыть проект") continue;
                backButton = new ToolStripButton("←") { ToolTipText = "Предыдущий XML · Alt+←", Padding = new Padding(4, 3, 4, 3) };
                forwardButton = new ToolStripButton("→") { ToolTipText = "Следующий XML · Alt+→", Padding = new Padding(4, 3, 4, 3) };
                backButton.Click += delegate { Guard(delegate { NavigateHistory(true); }); };
                forwardButton.Click += delegate { Guard(delegate { NavigateHistory(false); }); };
                strip.Items.Insert(0, new ToolStripSeparator()); strip.Items.Insert(0, forwardButton); strip.Items.Insert(0, backButton);
                break;
            }

            var selectionBar = Strip(); selectionBar.Dock = DockStyle.Bottom;
            selectionCount.Padding = new Padding(4, 0, 9, 0);
            selectionBar.Items.Add(selectionCount);
            arrangeButton = new ToolStripDropDownButton("Расположить");
            AddArrangeItems(arrangeButton.DropDownItems);
            selectionBar.Items.Add(arrangeButton);
            atlasButton = new ToolStripButton("Атлас") { ToolTipText = "Перейти к исходной области текстуры" };
            atlasButton.Click += delegate { Guard(JumpAtlas); };
            xmlButton = new ToolStripButton("Тег XML") { ToolTipText = "Показать выбранный тег в исходном XML" };
            xmlButton.Click += delegate { Guard(ShowInSource); };
            selectionBar.Items.Add(atlasButton); selectionBar.Items.Add(xmlButton);
            centerTabs.TabPages[0].Controls.Add(selectionBar);

            Canvas.MouseUp += delegate(object sender, MouseEventArgs e) {
                if (e.Button != MouseButtons.Right || Document == null) return;
                var hits = Canvas.HitsAt(e.Location);
                if (hits.Count > 0 && !Canvas.Selection.Contains(hits[0].Key)) Canvas.SelectKey(hits[0].Key, false);
                BuildCanvasMenu(hits); canvasMenu.Show(Canvas, e.Location);
            };
            tree.NodeMouseClick += delegate(object sender, TreeNodeMouseClickEventArgs e) {
                if (e.Button == MouseButtons.Right) { tree.SelectedNode = e.Node; BuildCanvasMenu(new List<UiNode>()); canvasMenu.Show(tree, e.Location); }
            };
            filterTimer.Tick += delegate {
                filterTimer.Stop();
                bool f = pendingFiles, n = pendingNodes, t = pendingTextures, find = pendingFind;
                pendingFiles = pendingNodes = pendingTextures = pendingFind = false;
                if (f) FillFiles(); if (n) FillTree(); if (t) FillTextures(); if (find) UpdateFindCount();
            };
            BuildFindBar();
            source.TextChanged += delegate { if (!binding) { sourceHistoryActive = true; QueueFilter("find"); UpdateWorkflowState(); } };
            source.SelectionChanged += delegate { if (!binding) UpdateWorkflowState(); };
            FormClosed += delegate { filterTimer.Stop(); filterTimer.Dispose(); canvasMenu.Dispose(); };
            UpdateWorkflowState();
        }

        void QueueFilter(string kind) {
            if (binding) return;
            if (kind == "files") pendingFiles = true;
            else if (kind == "nodes") pendingNodes = true;
            else if (kind == "textures") pendingTextures = true;
            else pendingFind = true;
            filterTimer.Stop(); filterTimer.Start();
        }

        void AddArrangeItems(ToolStripItemCollection items) {
            string[] labels = { "По левому краю", "По правому краю", "По верхнему краю", "По нижнему краю", "Центры по X", "Центры по Y", "Одинаковая ширина", "Одинаковая высота", "Одинаковый размер", "Равные интервалы по X", "Равные интервалы по Y" };
            string[] modes = { "left", "right", "top", "bottom", "centerx", "centery", "width", "height", "size", "distributex", "distributey" };
            for (int i = 0; i < modes.Length; i++) {
                if (i == 6 || i == 9) items.Add(new ToolStripSeparator());
                string mode = modes[i];
                var item = new ToolStripMenuItem(labels[i]) { ToolTipText = i < 9 ? "Относительно первого выбранного элемента; заблокированные пропускаются" : "Три или более элемента; крайние остаются на месте" };
                item.Click += delegate { Guard(delegate { Canvas.Align(mode); }); };
                items.Add(item);
            }
        }

        void BuildCanvasMenu(List<UiNode> hits) {
            while (canvasMenu.Items.Count > 0) { var old = canvasMenu.Items[0]; canvasMenu.Items.RemoveAt(0); old.Dispose(); }
            bool selected = Canvas.Primary != null;
            if (hits.Count > 1) {
                var under = new ToolStripMenuItem("Элементы под указателем (" + hits.Count + ")");
                foreach (var node in hits) {
                    string key = node.Key;
                    var item = new ToolStripMenuItem(node.Get("id", node.Name)) { ToolTipText = key, Checked = Canvas.Selection.Contains(key) };
                    item.Click += delegate { Canvas.SelectKey(key, false); };
                    under.DropDownItems.Add(item);
                    if (under.DropDownItems.Count >= 50) break;
                }
                canvasMenu.Items.Add(under); canvasMenu.Items.Add(new ToolStripSeparator());
            }
            ContextItem("Вписать выделение", Canvas.FitSelection, selected);
            ContextItem("Показать тег в XML", ShowInSource, selected);
            ContextItem("Перейти к атласу", JumpAtlas, selected && !Document.Atlas);
            var arrange = new ToolStripMenuItem("Расположить группу") { Enabled = Canvas.Selection.Count > 1 && !sourceDirty };
            AddArrangeItems(arrange.DropDownItems); canvasMenu.Items.Add(arrange);
            canvasMenu.Items.Add(new ToolStripSeparator());
            ContextItem("Дублировать основной элемент", Duplicate, selected && !sourceDirty);
            ContextItem("Удалить выделенное", Delete, selected && !sourceDirty);
            ContextItem("Скрыть выделенное", delegate { SetSelectionFlag(Document.Hidden, true); }, selected);
            ContextItem(selected && Document.Locked.Contains(Canvas.Primary.Key) ? "Разблокировать выделенное" : "Блокировать выделенное", delegate {
                SetSelectionFlag(Document.Locked, !Document.Locked.Contains(Canvas.Primary.Key));
            }, selected);
            canvasMenu.Items.Add(new ToolStripSeparator());
            ContextItem("Показать все скрытые элементы", delegate { Document.Hidden.Clear(); FillTree(); ShowSelection(); Canvas.Invalidate(); }, Document.Hidden.Count > 0);
            ContextItem("Разблокировать все элементы", delegate { Document.Locked.Clear(); FillTree(); ShowSelection(); Canvas.Invalidate(); }, Document.Locked.Count > 0);
            canvasMenu.BackColor = currentTheme.Panel; canvasMenu.ForeColor = currentTheme.Text; canvasMenu.Renderer = new ThemeRenderer(currentTheme);
            foreach (ToolStripItem item in canvasMenu.Items) {
                item.BackColor = currentTheme.Panel; item.ForeColor = currentTheme.Text;
                var drop = item as ToolStripDropDownItem;
                if (drop != null) { drop.DropDown.Renderer = new ThemeRenderer(currentTheme); foreach (ToolStripItem sub in drop.DropDownItems) { sub.ForeColor = currentTheme.Text; sub.BackColor = currentTheme.Panel; } }
            }
        }
        void ContextItem(string title, Action action, bool enabled) {
            var item = new ToolStripMenuItem(title) { Enabled = enabled };
            item.Click += delegate { Guard(action); }; canvasMenu.Items.Add(item);
        }
        void SetSelectionFlag(HashSet<string> flags, bool value) {
            foreach (string key in Canvas.Selection) { if (value) flags.Add(key); else flags.Remove(key); }
            FillTree(); ShowSelection(); Canvas.Invalidate();
        }

        TreeState CaptureTree() {
            var state = new TreeState { Top = tree.TopNode == null ? null : tree.TopNode.Tag as string };
            foreach (var pair in treeNodes) if (pair.Value.IsExpanded) state.Expanded.Add(pair.Key);
            return state;
        }
        void CaptureDocumentView() {
            if (Document == null) return;
            documentViews[Document.FilePath] = new DocumentView {
                Zoom = Canvas.Zoom, Pan = Canvas.Pan, Aspect = aspect.SelectedIndex, Atlas = Canvas.AtlasFile,
                Selection = new List<string>(Canvas.Selection), Tree = CaptureTree(), Filter = nodeSearch.Text,
                Tab = centerTabs.SelectedIndex, Caret = source.SelectionStart
            };
        }
        void RestoreDocumentView() {
            DocumentView view;
            if (Document == null || !documentViews.TryGetValue(Document.FilePath, out view)) { Canvas.Fit(); return; }
            bool old = binding; binding = true;
            aspect.SelectedIndex = view.Aspect;
            Canvas.Selection.Clear();
            foreach (string key in view.Selection) if (Document.Node(key) != null) Canvas.Selection.Add(key);
            Canvas.AtlasFile = view.Atlas; Canvas.Zoom = view.Zoom; Canvas.Pan = view.Pan;
            nodeSearch.Text = view.Filter; centerTabs.SelectedIndex = Document.ParseError == null ? view.Tab : 1;
            source.Select(Math.Min(source.TextLength, view.Caret), 0);
            binding = old;
            FillTree(); FillPages(); ShowSelection(); Canvas.Invalidate();
        }
        void ResetWorkflow() {
            documentViews.Clear(); backHistory.Clear(); forwardHistory.Clear(); treeDocument = null;
            filterTimer.Stop(); pendingFiles = pendingNodes = pendingTextures = pendingFind = false;
            bool old = binding; binding = true; fileSearch.Clear(); nodeSearch.Clear(); textureSearch.Clear(); binding = old;
            sourceHistoryActive = false; UpdateWorkflowState();
        }
        void NavigateHistory(bool backwards) {
            var from = backwards ? backHistory : forwardHistory;
            var to = backwards ? forwardHistory : backHistory;
            if (from.Count == 0 || Document == null) return;
            string previous = Document.FilePath, target = from.Peek();
            if (!OpenDocument(target, false)) return;
            from.Pop(); to.Push(previous); UpdateWorkflowState();
        }
        void RecordNavigation(string previous, string next) {
            if (previous == null || string.Equals(previous, next, StringComparison.OrdinalIgnoreCase)) return;
            backHistory.Push(previous); forwardHistory.Clear();
            if (backHistory.Count > 100) {
                string[] items = backHistory.ToArray(); backHistory.Clear();
                for (int i = 99; i >= 0; i--) backHistory.Push(items[i]);
            }
        }

        string ReadSourceText() {
            string value = source.Text;
            if (sourceBase.IndexOf("\r\n", StringComparison.Ordinal) >= 0)
                value = value.Replace("\r\n", "\n").Replace("\n", "\r\n");
            return value;
        }
        int SourceViewPosition(int documentOffset) {
            string prefix = Document.Text.Substring(0, Math.Min(documentOffset, Document.Text.Length));
            if (source.Text.IndexOf("\r\n", StringComparison.Ordinal) < 0) prefix = prefix.Replace("\r\n", "\n");
            return Math.Min(source.TextLength, prefix.Length);
        }

        void BuildFindBar() {
            var page = centerTabs.TabPages[1];
            findStrip = Strip(); findStrip.Visible = false;
            findText.AutoSize = false; findText.Width = 155; findText.ToolTipText = "Поиск буквального текста в текущем XML";
            findStrip.Items.Add(new ToolStripLabel("Найти:")); findStrip.Items.Add(findText);
            var previous = new ToolStripButton("↑") { ToolTipText = "Предыдущее · Shift+F3" };
            var next = new ToolStripButton("↓") { ToolTipText = "Следующее · F3" };
            previous.Click += delegate { FindSource(true); }; next.Click += delegate { FindSource(false); };
            findStrip.Items.Add(previous); findStrip.Items.Add(next); findStrip.Items.Add(findCase); findStrip.Items.Add(findCount);
            var close = new ToolStripButton("×") { Alignment = ToolStripItemAlignment.Right, ToolTipText = "Закрыть поиск · Esc" };
            close.Click += delegate { findStrip.Visible = false; source.Focus(); };
            findStrip.Items.Add(close);
            findText.TextChanged += delegate { QueueFilter("find"); };
            findCase.CheckedChanged += delegate { UpdateFindCount(); };
            findText.KeyDown += delegate(object sender, KeyEventArgs e) {
                if (e.KeyCode == Keys.Enter) { FindSource(e.Shift); e.SuppressKeyPress = true; }
                if (e.KeyCode == Keys.Escape) { findStrip.Visible = false; source.Focus(); e.SuppressKeyPress = true; }
            };
            page.Controls.Add(findStrip);
            sourceGutter = new SourceGutter(source) { Dock = DockStyle.Left, Width = 43, Palette = currentTheme };
            page.Controls.Add(sourceGutter);
        }
        void ShowFind() {
            if (Document == null) return;
            centerTabs.SelectedIndex = 1; findStrip.Visible = true;
            if (source.SelectionLength > 0 && source.SelectionLength < 160 && source.SelectedText.IndexOf('\n') < 0) findText.Text = source.SelectedText;
            findText.Focus(); findText.SelectAll(); UpdateFindCount();
        }
        void FindSource(bool backwards) {
            if (Document == null) return;
            if (findText.Text.Length == 0) { ShowFind(); return; }
            centerTabs.SelectedIndex = 1; findStrip.Visible = true;
            int start = backwards ? source.SelectionStart - 1 : source.SelectionStart + source.SelectionLength;
            int index = XmlSearch.Find(source.Text, findText.Text, start, backwards, findCase.Checked);
            if (index >= 0) { source.Select(index, findText.Text.Length); source.ScrollToCaret(); source.Focus(); }
            UpdateFindCount();
        }
        void UpdateFindCount() {
            if (findStrip == null || !findStrip.Visible) return;
            string query = findText.Text, text = source.Text;
            if (query.Length == 0) { findCount.Text = ""; return; }
            var comparison = findCase.Checked ? StringComparison.Ordinal : StringComparison.OrdinalIgnoreCase;
            int at = 0, count = 0, current = 0;
            while (at <= text.Length - query.Length && count <= 10000) {
                at = text.IndexOf(query, at, comparison); if (at < 0) break;
                count++; if (at == source.SelectionStart) current = count;
                at += query.Length;
            }
            findCount.Text = count == 0 ? "Нет совпадений" : (current > 0 ? current + " / " : "") + (count > 10000 ? "10000+" : count.ToString());
            findCount.ForeColor = count == 0 ? currentTheme.Accent : currentTheme.Muted;
        }
        void UpdateWorkflowState() {
            if (backButton != null) { backButton.Enabled = backHistory.Count > 0; forwardButton.Enabled = forwardHistory.Count > 0; }
            source.ReadOnly = Document == null;
            selectionCount.Text = "Выбрано: " + Canvas.Selection.Count;
            if (arrangeButton != null) arrangeButton.Enabled = Canvas.Selection.Count > 1 && !sourceDirty;
            if (atlasButton != null) atlasButton.Enabled = Document != null && !Document.Atlas && Canvas.Primary != null && UiLayout.TextureName(Document, Canvas.Primary) != "";
            if (xmlButton != null) xmlButton.Enabled = Canvas.Primary != null;
            if (sourceGutter != null) { sourceGutter.Palette = currentTheme; sourceGutter.Invalidate(); }
            foreach (Control control in Controls) {
                var strip = control as ToolStrip; if (strip == null || strip is MenuStrip || strip is StatusStrip) continue;
                foreach (ToolStripItem item in strip.Items) {
                    if (item.Text == "Сохранить") item.Enabled = Document != null && (Document.Dirty || sourceDirty);
                    else if (item.Text == "↶ Отмена") item.Enabled = sourceHistoryActive && centerTabs.SelectedIndex == 1 ? source.CanUndo : Document != null && Document.UndoStack.Count > 0;
                    else if (item.Text == "↷") item.Enabled = sourceHistoryActive && centerTabs.SelectedIndex == 1 ? source.CanRedo : Document != null && Document.RedoStack.Count > 0;
                }
            }
        }
    }

    sealed class SourceGutter : Control {
        readonly RichTextBox editor;
        public ThemePalette Palette;
        public SourceGutter(RichTextBox source) {
            editor = source; DoubleBuffered = true; Cursor = Cursors.Default;
            source.VScroll += delegate { Invalidate(); }; source.TextChanged += delegate { Invalidate(); };
            source.SelectionChanged += delegate { Invalidate(); }; source.Resize += delegate { Invalidate(); };
        }
        protected override void OnPaint(PaintEventArgs e) {
            if (Palette == null) return;
            e.Graphics.Clear(Palette.Panel);
            int first = editor.GetLineFromCharIndex(editor.GetCharIndexFromPosition(new Point(1, 1)));
            int selected = editor.GetLineFromCharIndex(editor.SelectionStart);
            int offset = editor.Top - Top;
            using (var pen = new Pen(Palette.Border)) e.Graphics.DrawLine(pen, Width - 1, 0, Width - 1, Height);
            for (int line = first; line < first + editor.Height / Math.Max(1, editor.Font.Height) + 3; line++) {
                int index = editor.GetFirstCharIndexFromLine(line); if (index < 0) break;
                int y = editor.GetPositionFromCharIndex(index).Y + offset;
                if (y > Height) break;
                TextRenderer.DrawText(e.Graphics, (line + 1).ToString(), editor.Font, new Rectangle(0, y, Width - 6, editor.Font.Height + 2), line == selected ? Palette.Accent : Palette.Muted, TextFormatFlags.Right | TextFormatFlags.NoPadding);
            }
        }
    }
}
