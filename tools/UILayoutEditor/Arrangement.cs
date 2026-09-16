using System;
using System.Collections.Generic;
using System.Drawing;

namespace HalkUIEditor {
    // Compute every change from the same snapshot, in screen coordinates.
    // The caller commits the complete operation as one undo step.
    public static class Arrangement {
        public static Dictionary<string, Dictionary<string, string>> Build(UiDocument document, IList<string> selection, string mode) {
            var result = new Dictionary<string, Dictionary<string, string>>();
            var eligible = new HashSet<string>();
            foreach (string key in selection) {
                var node = document.Node(key);
                if (node != null && node.Geometry && !document.Locked.Contains(key) && !UiLayout.IsHidden(document, node)) eligible.Add(key);
            }
            var nodes = new List<UiNode>();
            foreach (string key in selection) {
                if (!eligible.Contains(key)) continue;
                var node = document.Node(key);
                bool nested = false;
                int guard = 0;
                for (var parent = UiLayout.Parent(document, node); parent != null && guard++ < 80; parent = UiLayout.Parent(document, parent)) {
                    if (eligible.Contains(parent.Key)) { nested = true; break; }
                }
                if (!nested) nodes.Add(node);
            }
            bool horizontal = mode == "distributex", vertical = mode == "distributey";
            if (nodes.Count < (horizontal || vertical ? 3 : 2)) return result;
            var anchor = UiLayout.Rect(document, nodes[0]);
            if (horizontal || vertical) {
                nodes.Sort(delegate(UiNode a, UiNode b) {
                    var ra = UiLayout.Rect(document, a); var rb = UiLayout.Rect(document, b);
                    int order = (horizontal ? ra.Left : ra.Top).CompareTo(horizontal ? rb.Left : rb.Top);
                    return order == 0 ? a.Start.CompareTo(b.Start) : order;
                });
                var first = UiLayout.Rect(document, nodes[0]);
                var last = UiLayout.Rect(document, nodes[nodes.Count - 1]);
                float total = 0;
                foreach (var node in nodes) { var r = UiLayout.Rect(document, node); total += horizontal ? r.Width : r.Height; }
                float edge = horizontal ? first.Left : first.Top;
                float gap = ((horizontal ? last.Right : last.Bottom) - edge - total) / (nodes.Count - 1);
                for (int i = 0; i < nodes.Count; i++) {
                    var node = nodes[i]; var r = UiLayout.Rect(document, node);
                    // Keep both outside elements byte-for-byte unchanged.
                    if (i > 0 && i < nodes.Count - 1) result[node.Key] = new Dictionary<string, string> {
                        { horizontal ? "x" : "y", UiDocument.Num(node.Number(horizontal ? "x" : "y", 0) + edge - (horizontal ? r.Left : r.Top)) }
                    };
                    edge += (horizontal ? r.Width : r.Height) + gap;
                }
                return result;
            }
            foreach (var node in nodes) {
                if (node == nodes[0]) continue;
                var r = UiLayout.Rect(document, node); var values = new Dictionary<string, string>();
                switch (mode) {
                    case "left": values["x"] = UiDocument.Num(node.Number("x", 0) + anchor.Left - r.Left); break;
                    case "right": values["x"] = UiDocument.Num(node.Number("x", 0) + anchor.Right - r.Right); break;
                    case "top": values["y"] = UiDocument.Num(node.Number("y", 0) + anchor.Top - r.Top); break;
                    case "bottom": values["y"] = UiDocument.Num(node.Number("y", 0) + anchor.Bottom - r.Bottom); break;
                    case "centerx": values["x"] = UiDocument.Num(node.Number("x", 0) + anchor.Left + anchor.Width / 2 - r.Left - r.Width / 2); break;
                    case "centery": values["y"] = UiDocument.Num(node.Number("y", 0) + anchor.Top + anchor.Height / 2 - r.Top - r.Height / 2); break;
                    case "width": values["width"] = UiDocument.Num(anchor.Width); break;
                    case "height": values["height"] = UiDocument.Num(anchor.Height); break;
                    case "size": values["width"] = UiDocument.Num(anchor.Width); values["height"] = UiDocument.Num(anchor.Height); break;
                    default: throw new ArgumentException("Неизвестная команда расположения.");
                }
                if (values.Count > 0) result[node.Key] = values;
            }
            return result;
        }
    }
}
