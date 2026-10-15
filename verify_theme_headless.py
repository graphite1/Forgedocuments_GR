"""No Tk roots or GUI calls: enforce the Tomei theme selection contract."""
import ast,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from desktop_theme import configure_theme


class FakeStyle:
    def __init__(self,names=('vista','clam','default')):self.names=names;self.current='vista';self.calls=[]
    def theme_names(self):return self.names
    def theme_use(self,value):self.current=value;self.calls.append(value)


class StopAfterTheme(Exception):pass


class ThemeHeadlessChecks(unittest.TestCase):
    def test_real_form_entry_points_keep_tomei_theme_across_round_trips(self):
        from main_app import Home
        from ac_screen import App as AC
        from tomei_screen import App as Tomei
        from aktio_screen import App as Aktio
        state=FakeStyle()
        def apply_and_stop(root):
            configure_theme(style=state)
            raise StopAfterTheme()
        with tempfile.TemporaryDirectory() as folder,patch('tkinter.Tk',side_effect=AssertionError('GUI forbidden')),patch('tkinter.Toplevel',side_effect=AssertionError('GUI forbidden')),patch('tkinter.ttk.Style',side_effect=AssertionError('GUI forbidden')):
            for module,factory in [('main_app',Home),('definition_screen',Tomei),('ac_screen',AC),('definition_screen',Tomei),('ac_screen',AC),('aktio.ui',Aktio)]:
                with patch(module+'.configure_theme',side_effect=apply_and_stop),self.assertRaises(StopAfterTheme):factory(object(),folder)
                self.assertEqual(state.current,'vista')
        self.assertEqual(state.calls,['vista']*6)

    def test_non_windows_development_fallback_does_not_choose_ac_theme(self):
        style=FakeStyle(('clam','default'));self.assertEqual(configure_theme(style=style),'default')
        self.assertNotIn('clam',style.calls)

    def test_forms_cannot_bypass_shared_theme_or_reapply_ac_padding(self):
        root=Path(__file__).resolve().parent
        for name in ['main_app.py','ac_screen.py','definition_screen.py','aktio/ui.py']:
            tree=ast.parse((root/name).read_text(encoding='utf8'))
            calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
            self.assertFalse([n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='theme_use'],name)
            self.assertFalse([n for n in calls if isinstance(n.func,ast.Attribute) and n.func.attr=='Style'],name)
            self.assertFalse([n for n in ast.walk(tree) if isinstance(n,ast.Constant) and n.value=='clam'],name)

if __name__=='__main__':unittest.main(verbosity=2)
