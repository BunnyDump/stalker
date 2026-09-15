using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace HalkUIEditor {
    public sealed class XmlAttributeSpan {
        public string Name, Value; public int Start, Length, ValueStart, ValueLength; public char Quote;
    }
    public sealed class UiNode {
        public string Name, Key; public int Start, OpenEnd, CloseStart, End; public bool SelfClosing;
        public UiNode Parent; public List<UiNode> Children = new List<UiNode>();
        public List<XmlAttributeSpan> Attributes = new List<XmlAttributeSpan>();
        public string Get(string name, string fallback) { foreach (var a in Attributes) if (a.Name==name) return a.Value; return fallback; }
        public bool Has(string name) { return Get(name,null)!=null; }
        public float Number(string name, float fallback) { float v; return float.TryParse(Get(name,""),NumberStyles.Float,CultureInfo.InvariantCulture,out v) && !float.IsInfinity(v) && !float.IsNaN(v) ? v : fallback; }
        public UiNode Child(string name) { foreach(var n in Children) if(n.Name==name) return n; return null; }
        public string Content(string source) { return SelfClosing ? "" : LosslessXml.Decode(Regex.Replace(source.Substring(OpenEnd,Math.Max(0,CloseStart-OpenEnd)),@"<[^>]+>","").Trim()); }
        public RectangleF LocalRect { get { return new RectangleF(Number("x",0),Number("y",0),Math.Max(0,Number("width",0)),Math.Max(0,Number("height",0))); } }
        public bool Geometry { get { return Name!="texture" && (Has("x")||Has("y")||Has("width")||Has("height")) || Name=="texture" && Has("id"); } }
    }
    public sealed class LosslessXml {
        static readonly Regex Tokens = new Regex(@"<!--[\s\S]*?-->|<!\[CDATA\[[\s\S]*?\]\]>|<\?[\s\S]*?\?>|<![^>]*>|</?[A-Za-z_][\w:.-]*(?:[^>""']|""[^""]*""|'[^']*')*>",RegexOptions.Compiled);
        static readonly Regex Attrs = new Regex(@"(?<n>[A-Za-z_][\w:.-]*)\s*=\s*(?:""(?<d>[^""]*)""|'(?<s>[^']*)'|(?<b>[^\s/>]+))",RegexOptions.Compiled);
        public UiNode Root; public List<string> Diagnostics=new List<string>(); public List<UiNode> Nodes = new List<UiNode>();
        public Dictionary<string,UiNode> ByKey = new Dictionary<string,UiNode>();
        public static string Decode(string s) { return s.Replace("&lt;","<").Replace("&gt;",">").Replace("&quot;","\"").Replace("&apos;","'").Replace("&amp;","&"); }
        public static string Encode(string s) { return s.Replace("&","&amp;").Replace("<","&lt;").Replace(">","&gt;").Replace("\"","&quot;").Replace("'","&apos;"); }
        public LosslessXml(string source) {
            var stack = new Stack<UiNode>(); var roots=new List<UiNode>(); int last=0;
            foreach(Match m in Tokens.Matches(source)) {
                if(source.Substring(last,m.Index-last).IndexOf('<')>=0) throw new FormatException("Незавершённый XML-тег около позиции "+last);
                last=m.Index+m.Length; string t=m.Value;
                if(t.StartsWith("<!DOCTYPE",StringComparison.OrdinalIgnoreCase)) throw new FormatException("DTD в UI XML не поддерживается.");
                if(t.StartsWith("<!")||t.StartsWith("<?")) continue;
                bool close=t.StartsWith("</"); Match name=Regex.Match(t,@"^</?([A-Za-z_][\w:.-]*)");
                if(close) { if(stack.Count==0 || stack.Peek().Name!=name.Groups[1].Value) throw new FormatException("Несогласованный закрывающий тег "+t); var n=stack.Pop();n.CloseStart=m.Index;n.End=last;continue; }
                UiNode node=new UiNode();node.Name=name.Groups[1].Value;node.Start=m.Index;node.OpenEnd=last;node.SelfClosing=t.EndsWith("/>");node.Parent=stack.Count>0?stack.Peek():null;
                int ordinal=0;if(node.Parent!=null) foreach(var sibling in node.Parent.Children) if(sibling.Name==node.Name) ordinal++;
                node.Key=(node.Parent==null?"":node.Parent.Key+"/")+node.Name+"["+ordinal+"]";
                foreach(Match a in Attrs.Matches(t,name.Length)) {
                    if(node.Has(a.Groups["n"].Value)) Diagnostics.Add("Повтор атрибута "+a.Groups["n"].Value+" в <"+node.Name+">; редактируется первое значение.");
                    Group v=a.Groups["d"].Success?a.Groups["d"]:a.Groups["s"].Success?a.Groups["s"]:a.Groups["b"];
                    node.Attributes.Add(new XmlAttributeSpan {Name=a.Groups["n"].Value,Value=Decode(v.Value),Start=m.Index+a.Index,Length=a.Length,ValueStart=m.Index+v.Index,ValueLength=v.Length,Quote=a.Groups["d"].Success?'"':a.Groups["s"].Success?'\'':'\0'});
                }
                string attrs=t.Substring(name.Length,t.Length-name.Length-(node.SelfClosing?2:1));
                if(Attrs.Replace(attrs,"").Trim().Length>0) throw new FormatException("Некорректные атрибуты в <"+node.Name+">.");
                if(node.Parent!=null)node.Parent.Children.Add(node);else roots.Add(node);
                Nodes.Add(node);
                if(node.SelfClosing){node.CloseStart=last;node.End=last;}else stack.Push(node);
            }
            if(stack.Count!=0)throw new FormatException("XML не завершён: отсутствует закрывающий тег <"+stack.Peek().Name+">.");
            if(roots.Count==1)Root=roots[0];else {Root=new UiNode{Name="#fragment",Start=0,OpenEnd=0,CloseStart=source.Length,End=source.Length};Root.Children.AddRange(roots);foreach(var n in roots)n.Parent=Root;}
            AssignKeys(Root,"");
            if(source.Substring(last).IndexOf('<')>=0)throw new FormatException("Незавершённый тег в конце XML.");
        }
        void AssignKeys(UiNode n,string key){n.Key=key==""?n.Name+"[0]":key;ByKey[n.Key]=n;var counts=new Dictionary<string,int>();foreach(var c in n.Children){int count;counts.TryGetValue(c.Name,out count);counts[c.Name]=count+1;AssignKeys(c,n.Key+"/"+c.Name+"["+count+"]");}}
    }
    sealed class TextPatch { public int Start,Length; public string Value; }
    public sealed class UiDocument {
        public string FilePath,Text,SavedText,ParseError; public Encoding Encoding; public byte[] Preamble; byte[] baseline;
        public LosslessXml Xml; public Stack<string> UndoStack=new Stack<string>(),RedoStack=new Stack<string>();
        public readonly HashSet<string> Hidden=new HashSet<string>(),Locked=new HashSet<string>();
        public readonly Dictionary<string,string> PreviewParents=new Dictionary<string,string>(); public bool EngineParents=true;
        public bool Dirty { get { return Text!=SavedText; } }
        public bool Atlas { get {foreach(var n in Xml.Nodes)if(n.Name=="texture"&&n.Has("id")&&AtlasReference(n)!="")return true;return Xml.Root.Name=="ui_texture";} }
        public string AtlasReference(UiNode n){for(var p=n;p!=null;p=p.Parent){if(p.Name=="file"&&p.Has("name"))return p.Get("name","");var f=p.Child("file_name");if(f!=null)return f.Content(Text);}return "";}
        public string DefaultAtlasReference {get{foreach(var n in Xml.Nodes){string f=AtlasReference(n);if(f!="")return f;}return "";}}
        public void SetContent(string key,string content){var n=Node(key);if(n==null||n.Name=="#fragment")return;if(n.Children.Count>0)throw new InvalidOperationException("Для элемента с вложенными тегами используйте вкладку XML.");string v=LosslessXml.Encode(content);if(n.SelfClosing)SetText(Text.Remove(n.OpenEnd-2,2).Insert(n.OpenEnd-2,">"+v+"</"+n.Name+">"));else{string old=Text.Substring(n.OpenEnd,n.CloseStart-n.OpenEnd);string lead=Regex.Match(old,@"^\s*").Value,tail=Regex.Match(old,@"\s*$").Value;if(lead.Length==old.Length)tail="";SetText(Text.Remove(n.OpenEnd,old.Length).Insert(n.OpenEnd,lead+v+tail));}}
        public void SetTexture(string key,string value){var n=Node(key);if(n==null)return;if(Atlas){for(var p=n;p!=null;p=p.Parent){if(p.Name=="file"){SetAttribute(p.Key,"name",value);return;}var f=p.Child("file_name");if(f!=null){SetContent(f.Key,value);return;}}}else{var t=n.Child("texture")??n.Child("texture_e");if(t!=null){SetContent(t.Key,value);return;}if(n.SelfClosing)SetText(Text.Remove(n.OpenEnd-2,2).Insert(n.OpenEnd-2,"><texture>"+LosslessXml.Encode(value)+"</texture></"+n.Name+">"));else SetText(Text.Insert(n.CloseStart,"<texture>"+LosslessXml.Encode(value)+"</texture>"));}}
        public static UiDocument Load(string path) {
            byte[] b=File.ReadAllBytes(path); if(b.Length>16*1024*1024)throw new IOException("XML больше 16 МБ.");
            Encoding e;int skip=0;
            if(b.Length>=3&&b[0]==239&&b[1]==187&&b[2]==191){e=new UTF8Encoding(false,true);skip=3;}
            else if(b.Length>=2&&b[0]==255&&b[1]==254){e=new UnicodeEncoding(false,false,true);skip=2;}
            else if(b.Length>=2&&b[0]==254&&b[1]==255){e=new UnicodeEncoding(true,false,true);skip=2;}
            else {string head=System.Text.Encoding.ASCII.GetString(b,0,Math.Min(b.Length,250));if(Regex.IsMatch(head,"encoding\\s*=\\s*['\"](?:windows-1251|cp1251)",RegexOptions.IgnoreCase)) e=System.Text.Encoding.GetEncoding(1251);else {e=new UTF8Encoding(false,true);try{e.GetString(b);}catch(DecoderFallbackException){e=System.Text.Encoding.GetEncoding(1251);}}}
            var d=new UiDocument();d.FilePath=Path.GetFullPath(path);d.Encoding=System.Text.Encoding.GetEncoding(e.CodePage,EncoderFallback.ExceptionFallback,DecoderFallback.ExceptionFallback);d.Preamble=new byte[skip];Array.Copy(b,d.Preamble,skip);d.baseline=b;d.Text=e.GetString(b,skip,b.Length-skip);try{d.Xml=new LosslessXml(d.Text);}catch(FormatException ex){d.Xml=new LosslessXml("");d.ParseError=ex.Message;}d.SavedText=d.Text;return d;
        }
        public UiNode Node(string key){UiNode n;return key!=null&&Xml.ByKey.TryGetValue(key,out n)?n:null;}
        public void SetText(string text){var parsed=new LosslessXml(text);Text=text;Xml=parsed;ParseError=null;}
        public void Commit(string before){if(before==Text)return;UndoStack.Push(before);RedoStack.Clear();}
        public void RestoreText(string text){Text=text;try{Xml=new LosslessXml(text);ParseError=null;}catch(FormatException ex){Xml=new LosslessXml("");ParseError=ex.Message;}}
        public bool Undo(){if(UndoStack.Count==0)return false;RedoStack.Push(Text);RestoreText(UndoStack.Pop());return true;}
        public bool Redo(){if(RedoStack.Count==0)return false;UndoStack.Push(Text);RestoreText(RedoStack.Pop());return true;}
        public static string Num(float f){return Math.Round(f,3).ToString("0.###",CultureInfo.InvariantCulture);}
        public void SetAttributes(Dictionary<string,Dictionary<string,string>> changes){
            var patches=new List<TextPatch>();
            foreach(var entry in changes){var node=Node(entry.Key);if(node==null)continue;string added="";
                foreach(var v in entry.Value){XmlAttributeSpan found=null;foreach(var a in node.Attributes)if(a.Name==v.Key){found=a;break;}
                    if(found!=null){string value=LosslessXml.Encode(v.Value);if(found.Quote=='\0'&&Regex.IsMatch(value,@"[\s/>]"))value="\""+value+"\"";patches.Add(new TextPatch{Start=found.ValueStart,Length=found.ValueLength,Value=value});}
                    else{if(!Regex.IsMatch(v.Key,@"^[A-Za-z_][\w:.-]*$"))throw new FormatException("Некорректное имя атрибута.");added+=" "+v.Key+"=\""+LosslessXml.Encode(v.Value)+"\"";}
                }
                if(added.Length>0)patches.Add(new TextPatch{Start=node.OpenEnd-(node.SelfClosing?2:1),Length=0,Value=added});
            }
            patches.Sort(delegate(TextPatch a,TextPatch b){return b.Start.CompareTo(a.Start);});string result=Text;foreach(var p in patches)result=result.Remove(p.Start,p.Length).Insert(p.Start,p.Value);SetText(result);
        }
        public void SetAttribute(string key,string name,string value){var all=new Dictionary<string,Dictionary<string,string>>();all[key]=new Dictionary<string,string>();all[key][name]=value;SetAttributes(all);}
        public void RemoveAttribute(string key,string name){var n=Node(key);if(n==null)return;foreach(var a in n.Attributes)if(a.Name==name){SetText(Text.Remove(a.Start,a.Length));return;}}
        public void DeleteNodes(List<string> keys){var list=new List<UiNode>();foreach(var key in keys){var n=Node(key);if(n!=null&&n.Parent!=null){bool nested=false;foreach(var other in keys)if(other!=key&&key.StartsWith(other+"/",StringComparison.Ordinal))nested=true;if(!nested)list.Add(n);}}
            list.Sort(delegate(UiNode a,UiNode b){return b.Start.CompareTo(a.Start);});string t=Text;foreach(var n in list)t=t.Remove(n.Start,n.End-n.Start);SetText(t);
        }
        public string Duplicate(string key){var n=Node(key);if(n==null||n.Parent==null)return key;string block=Text.Substring(n.Start,n.End-n.Start);string nl=Text.IndexOf("\r\n",StringComparison.Ordinal)>=0?"\r\n":"\n";SetText(Text.Insert(n.End,nl+"    "+block));UiNode copy=null;foreach(var c in Xml.Nodes)if(c.Start>n.Start&&c.Name==n.Name&&c.Parent!=null&&c.Parent.Key==n.Parent.Key){copy=c;break;}if(copy!=null){if(copy.Has("id")){string id=copy.Get("id","")+"_copy";int count=2;bool exists=true;while(exists){exists=false;foreach(var item in Xml.Nodes)if(item!=copy&&item.Get("id",null)==id)exists=true;if(exists)id=copy.Get("id","")+"_copy"+(count++);}SetAttribute(copy.Key,"id",id);}else{var values=new Dictionary<string,string>();if(copy.Has("x"))values["x"]=Num(copy.Number("x",0)+8);if(copy.Has("y"))values["y"]=Num(copy.Number("y",0)+8);var changes=new Dictionary<string,Dictionary<string,string>>();changes[copy.Key]=values;SetAttributes(changes);}return copy.Key;}return key;}
        public byte[] Bytes(){byte[] body=Encoding.GetBytes(Text);byte[] all=new byte[Preamble.Length+body.Length];Array.Copy(Preamble,all,Preamble.Length);Array.Copy(body,0,all,Preamble.Length,body.Length);return all;}
        static bool Equal(byte[] a,byte[] b){if(a==null||b==null||a.Length!=b.Length)return false;for(int i=0;i<a.Length;i++)if(a[i]!=b[i])return false;return true;}
        public string Save(string path){
            path=Path.GetFullPath(path);bool same=string.Equals(path,FilePath,StringComparison.OrdinalIgnoreCase);
            if(same&&File.Exists(path)&&!Equal(baseline,File.ReadAllBytes(path)))throw new IOException("Файл изменён другой программой. Перезагрузите его или используйте «Сохранить как».");
            byte[] data=Bytes();if(same&&Equal(data,baseline)&&File.Exists(path))return "";
            string dir=Path.GetDirectoryName(path);Directory.CreateDirectory(dir);string temp=Path.Combine(dir,"."+Path.GetFileName(path)+"."+Guid.NewGuid().ToString("N")+".tmp");string backup="";
            try{using(var f=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){f.Write(data,0,data.Length);f.Flush();}
                if(File.Exists(path)){backup=path+".bak."+DateTime.Now.ToString("yyyyMMdd_HHmmss_fff")+"."+Guid.NewGuid().ToString("N").Substring(0,4);File.Replace(temp,path,backup);}else File.Move(temp,path);
                FilePath=path;baseline=data;SavedText=Text;return backup;
            }finally{if(File.Exists(temp))File.Delete(temp);}
        }
    }
    public sealed class TextureRegion {public string Id,FileReference,FilePath,OwnerFile,NodeKey;public RectangleF Source;}
    public sealed class Workspace : IDisposable {
        public string Root,ActiveFile,TextureDirectory; public List<string> Files=new List<string>(),ImageFiles=new List<string>(),Warnings=new List<string>();
        public Dictionary<string,UiDocument> Documents=new Dictionary<string,UiDocument>(StringComparer.OrdinalIgnoreCase);
        public Dictionary<string,TextureRegion> Textures=new Dictionary<string,TextureRegion>(StringComparer.OrdinalIgnoreCase);
        List<TextureRegion> regions=new List<TextureRegion>();
        Dictionary<string,Bitmap> images=new Dictionary<string,Bitmap>(StringComparer.OrdinalIgnoreCase);
        LinkedList<string> imageOrder=new LinkedList<string>();long imageBytes;
        public Workspace(string root){Root=Path.GetFullPath(root);Scan(Root,0);Files.Sort(StringComparer.OrdinalIgnoreCase);ImageFiles.Sort(StringComparer.OrdinalIgnoreCase);ActiveFile=Files.Count>0?Files[0]:null;Reindex();}
        void Scan(string dir,int depth){if(depth>16||Files.Count>5000||ImageFiles.Count>30000)return;try{foreach(string p in Directory.GetFiles(dir)){string ext=Path.GetExtension(p).ToLowerInvariant();if(ext==".xml"&&Path.GetFileName(p).IndexOf(".bak.",StringComparison.OrdinalIgnoreCase)<0&& !p.EndsWith(".halk.xml",StringComparison.OrdinalIgnoreCase))Files.Add(p);else if(ext==".dds"||ext==".png"||ext==".bmp"||ext==".jpg"||ext==".jpeg")ImageFiles.Add(p);}
                foreach(string sub in Directory.GetDirectories(dir)){string n=Path.GetFileName(sub).ToLowerInvariant();if(n==".git"||n=="bin"||n=="obj"||n=="originals"||n=="backups")continue;if((File.GetAttributes(sub)&FileAttributes.ReparsePoint)!=0)continue;Scan(sub,depth+1);}}
            catch(UnauthorizedAccessException){Warnings.Add("Нет доступа: "+dir);}catch(IOException e){Warnings.Add(e.Message);}}
        public static string Variant(string path){if(path==null)return "";var m=Regex.Match(path.Replace('\\','/'),@"(?:^|/)(?:config|configs|textures)/(ui[^/]*)(?:/|$)",RegexOptions.IgnoreCase);return m.Success?m.Groups[1].Value.ToLowerInvariant():"";}
        public string ActiveVariant {get{return Variant(ActiveFile);}}
        public UiDocument Open(string path){path=Path.GetFullPath(path);UiDocument d;if(!Documents.TryGetValue(path,out d)){d=UiDocument.Load(path);Documents[path]=d;}return d;}
        public void Activate(UiDocument d){ActiveFile=d.FilePath;BuildIndex();}
        public void Reindex(){regions.Clear();Warnings.Clear();foreach(string p in Files){try{var d=Open(p);if(d.ParseError!=null){Warnings.Add(Path.GetFileName(p)+": "+d.ParseError);continue;}if(!d.Atlas)continue;foreach(var n in d.Xml.Nodes){if(n.Name!="texture"||!n.Has("id"))continue;string reference=d.AtlasReference(n);if(reference=="")continue;regions.Add(new TextureRegion{Id=n.Get("id",""),FileReference=reference,Source=n.LocalRect,OwnerFile=p,NodeKey=n.Key});}}
            catch(Exception e){Warnings.Add(Path.GetFileName(p)+": "+e.Message);}}BuildIndex();}
        void BuildIndex(){Textures.Clear();string variant=ActiveVariant;foreach(var r in regions){string v=Variant(r.OwnerFile);if(v!=variant&&v!="")continue;TextureRegion previous;if(Textures.TryGetValue(r.Id,out previous)){if(Variant(previous.OwnerFile)==variant)continue;}r.FilePath=ResolveFile(r.FileReference,r.OwnerFile);Textures[r.Id]=r;}}
        static string Native(string path){return path.Replace('\\',Path.DirectorySeparatorChar).Replace('/',Path.DirectorySeparatorChar);}
        public string ResolveFile(string reference){return ResolveFile(reference,ActiveFile);}
        public string ResolveFile(string reference,string owner){if(string.IsNullOrEmpty(reference))return null;string s=Native(reference);if(Path.IsPathRooted(s)&&File.Exists(s))return s;string variant=Variant(owner);var roots=new List<string>();
            if(!string.IsNullOrEmpty(TextureDirectory))roots.Add(TextureDirectory);roots.Add(Path.Combine(Root,"textures"));roots.Add(Root);
            foreach(string root in roots){string mapped=s;if(variant!=""&&(s.StartsWith("ui"+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)))mapped=variant+s.Substring(2);
                foreach(string relative in new[]{mapped,s,Path.GetFileName(s)})foreach(string suffix in new[]{"",".dds",".png",".bmp"}){string p=Path.Combine(root,relative+suffix);if(File.Exists(p))return p;}}
            string basename=Path.GetFileNameWithoutExtension(s);string match=null;int count=0;foreach(string p in ImageFiles){if(!string.Equals(Path.GetFileNameWithoutExtension(p),basename,StringComparison.OrdinalIgnoreCase))continue;string v=Variant(p);if(variant!=""&&v!=""&&v!=variant)continue;if(v==variant&&v!="")return p;match=p;count++;}return count==1?match:null;
        }
        public TextureRegion Resolve(string id){TextureRegion r;if(string.IsNullOrEmpty(id))return null;if(Textures.TryGetValue(id,out r))return r;if(Textures.TryGetValue(id+"_e",out r))return r;string p=ResolveFile(id);if(p==null)return null;Bitmap b=Image(p);return new TextureRegion{Id=id,FileReference=id,FilePath=p,Source=new RectangleF(0,0,b.Width,b.Height)};}
        public Bitmap Image(string path){if(path==null)return null;Bitmap b;if(images.TryGetValue(path,out b)){imageOrder.Remove(path);imageOrder.AddLast(path);return b;}b=TextureLoader.Load(path);long size=(long)b.Width*b.Height*4;while(imageBytes+size>160L*1024*1024&&imageOrder.Count>0){string old=imageOrder.First.Value;imageOrder.RemoveFirst();var im=images[old];imageBytes-=(long)im.Width*im.Height*4;im.Dispose();images.Remove(old);}images[path]=b;imageOrder.AddLast(path);imageBytes+=size;return b;}
        public void Dispose(){foreach(var b in images.Values)b.Dispose();images.Clear();imageOrder.Clear();imageBytes=0;}
        public static string FindRoot(string xml){var d=new DirectoryInfo(Path.GetDirectoryName(Path.GetFullPath(xml)));for(int i=0;d!=null&&i<8;i++,d=d.Parent){if(d.Name.Equals("gamedata",StringComparison.OrdinalIgnoreCase)||Directory.Exists(Path.Combine(d.FullName,"textures")))return d.FullName;}return Path.GetDirectoryName(Path.GetFullPath(xml));}
    }
    public static class UiLayout {
        public static string TextureName(UiDocument d,UiNode n){if(d.Atlas)return d.AtlasReference(n);var t=n.Child("texture")??n.Child("texture_e");return t==null?"":t.Content(d.Text);}
        public static UiNode Parent(UiDocument d,UiNode n){if(d.Atlas||n.Parent==null||n.Name=="main")return null;string parent;if(d.PreviewParents.TryGetValue(n.Key,out parent))return parent=="@origin"?null:d.Node(parent);if(!d.EngineParents||n.Parent!=d.Xml.Root)return n.Parent;
            string special=null;if(n.Name=="dragdrop_bag")special="bag_static";else if(n.Name.StartsWith("progress_bar_",StringComparison.Ordinal)&&n.Name!="progress_bar_rank")special="progress_background";else if(n.Name=="time_static_str")special="time_static";else if(n.Name=="dragdrop_list_our")special="our_bag_static";else if(n.Name=="dragdrop_list_other")special="others_bag_static";else if(n.Name=="descr_static"&&d.Xml.Root.Child("our_bag_static")!=null)special="frame_window";
            UiNode p=special==null?null:d.Xml.Root.Child(special);return p??d.Xml.Root.Child("main");}
        public static RectangleF Rect(UiDocument d,UiNode n){RectangleF r=n.LocalRect;UiNode p=Parent(d,n);int guard=0;while(p!=null&&guard++<40){r.Offset(p.Number("x",0),p.Number("y",0));p=Parent(d,p);}return r;}
        public static bool IsHidden(UiDocument d,UiNode n){for(var p=n;p!=null;p=p.Parent)if(d.Hidden.Contains(p.Key))return true;return false;}
        public static List<UiNode> Visible(UiDocument d){var list=new List<UiNode>();foreach(var n in d.Xml.Nodes)if(n.Geometry&&n.Name!="main"&&!IsHidden(d,n)){RectangleF r=Rect(d,n);if(r.Width>0&&r.Height>0)list.Add(n);}return list;}
        public static List<string> Validate(UiDocument d,Workspace w){var warnings=new List<string>(d.Xml.Diagnostics);var missing=new HashSet<string>();foreach(var n in d.Xml.Nodes){if(n.Geometry){foreach(string a in new[]{"x","y","width","height","cell_width","cell_height"})if(n.Has(a)){float v;if(!float.TryParse(n.Get(a,""),NumberStyles.Float,CultureInfo.InvariantCulture,out v)||float.IsNaN(v)||float.IsInfinity(v))warnings.Add(n.Name+": некорректный "+a);else if(a!="x"&&a!="y"&&v<0)warnings.Add(n.Name+": отрицательный "+a);}
                    if(n.Has("cell_width")&&n.Has("cols_num")&&n.Number("cell_width",0)*n.Number("cols_num",1)>n.Number("width",0)+.1f)warnings.Add(n.Name+": ячейки шире контейнера.");
                    if(n.Has("cell_height")&&n.Has("rows_num")&&n.Number("cell_height",0)*n.Number("rows_num",1)>n.Number("height",0)+.1f)warnings.Add(n.Name+": ячейки выше контейнера.");}
                string tex=TextureName(d,n);if(tex!=""&&w.ResolveFile(tex)==null&&!w.Textures.ContainsKey(tex)&&!w.Textures.ContainsKey(tex+"_e")&&missing.Add(tex))warnings.Add(n.Name+": не найдена текстура "+tex);}
            if(d.Atlas){foreach(var n in d.Xml.Root.Children)if(n.Name=="texture"){var tr=w.Resolve(n.Get("id",""));if(tr!=null&&tr.FilePath!=null){var b=w.Image(tr.FilePath);RectangleF r=n.LocalRect;if(r.X<0||r.Y<0||r.Right>b.Width||r.Bottom>b.Height)warnings.Add(n.Get("id",n.Name)+": вырезка за пределами DDS.");}}}return warnings;}
    }
}
