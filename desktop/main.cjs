const {app,BrowserWindow,shell}=require('electron');
const path=require('path');
function createWindow(){
 const win=new BrowserWindow({width:1440,height:920,minWidth:1000,minHeight:700,
  backgroundColor:'#080d18',autoHideMenuBar:true,
  webPreferences:{contextIsolation:true,nodeIntegration:false,sandbox:true}});
 win.loadFile(path.join(__dirname,'renderer','index.html'));
 win.webContents.setWindowOpenHandler(({url})=>{shell.openExternal(url);return {action:'deny'}});
}
app.whenReady().then(()=>{createWindow();app.on('activate',()=>{if(BrowserWindow.getAllWindows().length===0)createWindow()})});
app.on('window-all-closed',()=>{if(process.platform!=='darwin')app.quit()});
