using System;
using System.IO;
using System.Windows.Forms;
using System.Reflection;
[assembly: AssemblyTitle("X-Ray UI Editor")]
[assembly: AssemblyDescription("Offline XML and DDS layout editor")]
[assembly: AssemblyVersion("1.2.0.0")]
[assembly: AssemblyFileVersion("1.2.0.0")]
[assembly: AssemblyProduct("X-Ray UI Editor")]
namespace HalkUIEditor {
    static class Program {
        [STAThread] static int Main(string[] args){
            try {
                if(args.Length>=2&&args[0]=="--self-test")return SelfTest.Run(args[1]);
                if(args.Length>=3&&args[0]=="--validate-folder")return SelfTest.ValidateFolder(args[1],args[2]);
                Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
                Application.ThreadException+=delegate(object s,System.Threading.ThreadExceptionEventArgs e){if(args.Length>0&&args[0].StartsWith("--")){File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"editor-error.txt"),e.Exception.ToString());Environment.Exit(2);return;}MessageBox.Show(e.Exception.Message,"Ошибка редактора",MessageBoxButtons.OK,MessageBoxIcon.Warning);};
                var form=new MainForm();string open=args.Length>0&&!args[0].StartsWith("--")?args[0]:null;
                if(args.Length>=3&&args[0]=="--smoke-output"){open=args[2];string output=args[1];form.Shown+=delegate{form.BeginInvoke((MethodInvoker)delegate{form.SmokeOutput(output);});};}
                if(open==null){string sample=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"example");if(Directory.Exists(sample))open=sample;}
                if(open!=null){string initial=open;form.Load+=delegate{form.Guard(delegate{if(Directory.Exists(initial))form.OpenWorkspace(initial,null);else form.OpenWorkspace(Workspace.FindRoot(initial),initial);});};}
                Application.Run(form);return 0;
            }catch(Exception ex){try{File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"editor-error.txt"),ex.ToString());}catch(Exception){}if(args.Length>0&&args[0].StartsWith("--")){Console.Error.WriteLine(ex);return 1;}MessageBox.Show(ex.Message,"X-Ray UI Editor",MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        }
    }
}
