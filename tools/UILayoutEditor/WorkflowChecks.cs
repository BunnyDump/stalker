using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace HalkUIEditor {
    static class WorkflowChecks {
        static void Check(bool value, string label) { if (!value) throw new InvalidOperationException("1.2 regression: " + label); }
        static object Call(MainForm form, string name, params object[] args) { return typeof(MainForm).GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic).Invoke(form, args); }
        static T Field<T>(MainForm form, string name) { return (T)typeof(MainForm).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(form); }
        static UiDocument Make(string path, string text) { Directory.CreateDirectory(Path.GetDirectoryName(path)); File.WriteAllText(path, text, new UTF8Encoding(false)); return UiDocument.Load(path); }
        public static int Core(string folder) {
            int count = 0;
            Check(LosslessXml.Decode("&#38;lt; &amp;lt; &#x26;#65; &#38;amp;") == "&lt; &lt; &#65; &amp;", "numeric ampersands are decoded exactly once"); count++;
            var empty = Make(Path.Combine(folder, "empty-attribute.xml"), "<window value=abc/>");
            empty.SetAttribute(empty.Xml.Root.Key, "value", "");
            Check(empty.Xml.Root.Get("value", "missing") == "" && empty.Text.Contains("value=\"\""), "empty bare attribute receives quotes"); count++;
            string path = Path.Combine(folder, "arrange.xml");
            var d = Make(path, "<window><main x='10' y='20'/><first x='0' y='0' width='20' height='30'/><second x='40' y='30' width='10' height='10'/><third x='130' y='80' width='30' height='20'/><container x='200' y='100' width='100' height='80'><child x='9' y='7' width='10' height='10'/></container></window>");
            string original = d.Text;
            string first = d.Xml.Root.Child("first").Key, second = d.Xml.Root.Child("second").Key, third = d.Xml.Root.Child("third").Key;
            string container = d.Xml.Root.Child("container").Key, child = d.Node(container).Child("child").Key;
            var keys = new List<string> { first, second, third };
            d.SetAttributes(Arrangement.Build(d, keys, "distributex")); d.Commit(original);
            Check(d.Node(second).Number("x", 0) == 70 && d.Node(first).Number("x", -1) == 0 && d.Node(third).Number("x", 0) == 130, "equal gaps preserve outside bounds"); count++;
            d.Undo(); Check(d.Text == original, "group operation is one lossless undo"); count++;
            d.SetAttributes(Arrangement.Build(d, new List<string> { first, child }, "right"));
            Check(d.Node(child).Number("x", 0) == -190 && UiLayout.Rect(d, d.Node(child)).Right == UiLayout.Rect(d, d.Node(first)).Right, "align across different parents uses world coordinates"); count++;
            d.SetText(original); d.SetAttributes(Arrangement.Build(d, new List<string> { first, second }, "bottom"));
            Check(d.Node(second).Number("y", 0) == 20, "bottom alignment"); count++;
            d.SetText(original); d.SetAttributes(Arrangement.Build(d, new List<string> { first, second }, "size"));
            Check(d.Node(second).Number("width", 0) == 20 && d.Node(second).Number("height", 0) == 30 && d.Node(second).Number("x", 0) == 40, "match size preserves position"); count++;
            d.SetText(original); d.Locked.Add(second);
            Check(Arrangement.Build(d, keys, "distributex").Count == 0, "distribution needs three unlocked elements"); count++;
            d.Locked.Clear(); d.Hidden.Add(second);
            Check(Arrangement.Build(d, keys, "distributex").Count == 0, "hidden elements excluded"); count++;
            d.Hidden.Clear();
            var changes = Arrangement.Build(d, new List<string> { first, container, child }, "left");
            Check(changes.ContainsKey(container) && !changes.ContainsKey(child), "nested group does not move child twice"); count++;
            Check(XmlSearch.Find("один ДВА один", "ОДИН", 1, false, false) == 9, "Cyrillic case-insensitive search"); count++;
            Check(XmlSearch.Find("один ДВА один", "один", 13, false, true) == 0, "forward search wraps"); count++;
            Check(XmlSearch.Find("a aba", "a", -1, true, true) == 4, "backward search wraps"); count++;
            Check(XmlSearch.Find("abc", "abcd", 0, false, false) == -1 && XmlSearch.Find("abc", "", 0, false, false) == -1, "empty and overlong query"); count++;

            string images = Path.Combine(folder, "owner-paths");
            foreach (string name in new[] { "a", "b" }) {
                string dir = Path.Combine(images, name); Make(Path.Combine(dir, "layout.xml"), "<window/>");
                using (var image = new Bitmap(4, 4)) { image.SetPixel(0, 0, name == "a" ? Color.Red : Color.Blue); image.Save(Path.Combine(dir, "local.png")); }
            }
            using (var w = new Workspace(images)) {
                string a = w.ResolveFile("local", Path.Combine(images, "a/layout.xml"));
                string b = w.ResolveFile("local", Path.Combine(images, "b/layout.xml"));
                Check(a != b && w.Image(a).GetPixel(0, 0).R == 255 && w.Image(b).GetPixel(0, 0).B == 255, "relative images and owner-aware cache"); count++;
                var atlas = Make(Path.Combine(images, "a/atlas.xml"), "<w><file name='local.png'><texture id='outside' x='3' y='0' width='4' height='4'/></file><file name='local.png'><texture id='inside' x='0' y='0' width='4' height='4'/></file></w>");
                w.Activate(atlas); var warnings = UiLayout.Validate(atlas, w);
                Check(warnings.Count == 1 && warnings[0].StartsWith("outside:"), "nested atlas validation checks each own sheet"); count++;
                File.WriteAllText(Path.Combine(images, "a/broken.dds"), "not a texture");
                atlas.SetText("<w><file name='broken.dds'><texture id='broken' x='0' y='0' width='4' height='4'/></file></w>");
                warnings = UiLayout.Validate(atlas, w);
                Check(warnings.Count > 0 && warnings[warnings.Count - 1].StartsWith("broken.dds:"), "corrupt atlas image becomes diagnostic"); count++;
            }
            return count;
        }

        public static void UI(MainForm form) {
            Rectangle work = Screen.FromControl(form).WorkingArea;
            if (work.Width >= form.MinimumSize.Width && work.Height >= form.MinimumSize.Height)
                Check(work.Contains(form.Bounds), "window fits working area without taskbar overlap");
            var d = form.Document; var c = form.Canvas; string original = d.Text;
            string first = d.Xml.Root.Child("dragdrop_pistol").Key, second = d.Xml.Root.Child("dragdrop_automatic").Key, third = d.Xml.Root.Child("dragdrop_belt").Key;
            c.SelectKey(first, false); c.SelectKey(second, true); c.SelectKey(third, true);
            c.Align("distributex");
            Check(d.Node(second).Number("x", 0) == 161 && d.Node(first).Number("x", 0) == 42 && d.Node(third).Number("x", 0) == 280, "GUI distributes three actual slots");
            Call(form, "Undo"); Check(d.Text == original, "GUI distribution undo");
            c.FitSelection();
            foreach (string key in c.Selection) { var r = c.ScreenRect(UiLayout.Rect(d, d.Node(key))); Check(r.Left >= 0 && r.Right <= c.Width && r.Bottom <= c.Height && r.Top >= 0, "fit contains whole selection"); }
            c.SelectKey(first, false); c.SetZoom(1.75f); c.Pan = new PointF(-123, 45);
            var texture = form.Workspace.Resolve("sample_slot");
            form.OpenDocument(texture.OwnerFile); c.SelectKey(texture.NodeKey, false);
            Call(form, "NavigateHistory", true);
            Check(form.Document == d && c.Zoom == 1.75f && c.Pan == new PointF(-123, 45) && c.Primary.Key == first, "back restores document viewport and selection");
            Call(form, "NavigateHistory", false); Check(form.Document.Atlas && c.Primary.Key == texture.NodeKey, "forward restores atlas selection");
            Call(form, "NavigateHistory", true);
            var treeNodes = Field<Dictionary<string, TreeNode>>(form, "treeNodes"); string branch = d.Xml.Root.Child("background").Key;
            treeNodes[branch].Collapse(); c.MoveSelected(1, 0);
            Check(!Field<Dictionary<string, TreeNode>>(form, "treeNodes")[branch].IsExpanded, "editing preserves collapsed tree branches");
            Call(form, "Undo");
            var source = Field<RichTextBox>(form, "source");
            source.Select(0, 0); Call(form, "ShowFind");
            Field<ToolStripTextBox>(form, "findText").Text = "dragdrop_automatic"; Call(form, "FindSource", false);
            Check(source.SelectedText == "dragdrop_automatic" && d.Text == original, "GUI source search changes selection only");
            source.ClearUndo(); source.Select(source.TextLength, 0); source.SelectedText = "\r\n<!-- native history check -->";
            string edited = source.Text; Check(source.CanUndo && Field<bool>(form, "sourceDirty"), "raw source edit has native undo");
            c.SelectKey(second, true); c.Align("right"); Check(d.Text == original, "real pending source prevents canvas mutation");
            Call(form, "Undo"); Check(source.Text == original && !Field<bool>(form, "sourceDirty"), "raw undo reaches clean document");
            Call(form, "Redo"); Check(source.Text == edited, "raw redo still works after reaching clean document");
            Call(form, "Undo");
            Field<ThemeTabs>(form, "centerTabs").SelectedIndex = 0;
            c.SelectKey(first, false); c.MoveSelected(1, 0); Call(form, "Undo");
            var hits = new List<UiNode> { d.Node(first), d.Xml.Root.Child("background") };
            Call(form, "BuildCanvasMenu", hits); Call(form, "BuildCanvasMenu", hits);
            Check(Field<ContextMenuStrip>(form, "canvasMenu").Items.Count >= 10, "context menu can rebuild safely");
            Check(d.Text == original && source.Text == original, "new GUI workflows preserve original after undo");
            d.SetText(original.Replace("\n", "\r\n")); Call(form, "RefreshDocument", false);
            c.SelectKey(second, false); Call(form, "ShowInSource");
            Check(source.SelectedText.StartsWith("<dragdrop_automatic"), "show tag maps CRLF offsets to native editor");
            source.ClearUndo(); source.Select(source.TextLength, 0); source.SelectedText = "<!-- CRLF test -->";
            Call(form, "Undo"); Check(!Field<bool>(form, "sourceDirty"), "raw undo recognizes clean CRLF source");
            source.SelectedText = "<!-- CRLF test -->";
            Check(((string)Call(form, "ReadSourceText")).Contains("\r\n"), "source editing preserves Windows newlines");
            // Restore in memory; fixture files are never saved by the GUI checks.
            typeof(MainForm).GetField("sourceDirty", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(form, false);
            d.SetText(original); Call(form, "RefreshDocument", false);
            Field<ThemeTabs>(form, "centerTabs").SelectedIndex = 0;
            c.Fit(); c.SelectKey(first, false);
        }
    }
}
