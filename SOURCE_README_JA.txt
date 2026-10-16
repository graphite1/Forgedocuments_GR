Forgedocuments GR ソースコード版（Windows x64）

このsourceフォルダーはEXE版と同じ実装コミットのソースです。
出典コミットはsource-manifest.jsonに記録しています。

必要な環境：Python 3.14 x64（tkinter・venv・pipを含む通常のWindows版）。
既にあるPythonを使います。このBATはPythonのインストール、システムPATH、レジストリ、システムPythonのパッケージを変更しません。
Pythonがない場合は https://www.python.org/downloads/windows/ の公式手順で利用者が準備してください。
PATHを変更する必要はありません。Python Launcherのpy -3.14が使えます。
個別のpython.exeを指定するときは、コマンド画面で一時的に
 set "FORGE_SOURCE_PYTHON=C:\Python314\python.exe"
としてからsetup_source.batを実行してください。永続設定は行いません。

初回：
1. ZIP全体を、書き込み可能な新しい場所へ展開します。
2. sourceフォルダー内のsetup_source.batを実行します。
3. .source-venvを新規作成し、その中にrequirements.txtの固定版の依存をpipで導入します。
   この初回手順はネットワーク接続が必要です。管理者権限は不要です。
4. 成功したらstart_source.batで起動します。2回目以降もstart_source.batを使用します。

保存先：
ソース版はsource/source-runtime/data/<帳票ID>に保存します。
EXE版のdataフォルダーや既存のAPPDATA設定と共有しません。
ソース版の設定用APPDATA/LOCALAPPDATAも、この起動プロセス内だけsource-runtime配下へ分離します。
移動・バックアップ時はsource-runtimeを一緒に保持してください。
ソース版のアプリ内更新はEXE用更新を適用しません。新しい配布のソースへ更新してください。

依存：requirements.txt。再ビルドする開発者向けの追加依存はrequirements-build.txt。
元リポジトリにアプリ本体のLICENSEファイルはありません。この配布で新しい利用許諾を付与していません。
第三者のライセンスと著作権表示はTHIRD_PARTY_NOTICES.mdとthird_party_licenses/を参照してください。
PyMuPDFはAGPL-3.0またはArtifexの商用ライセンスという配布元表記です。同梱した条文も確認してください。

クラウドでは、クリーンな展開先からsetup_source.batとstart_source.batによるヘッドレス診断を検証します。
実GUIと実プリンターの動作確認は、この診断の成功とは別であり未検証です。
