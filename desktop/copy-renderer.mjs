import fs from 'node:fs'
import path from 'node:path'
const source=path.resolve('../frontend/dist')
const target=path.resolve('renderer')
if(!fs.existsSync(path.join(source,'index.html'))){
  console.error('Build the frontend first: cd ../frontend && npm run build')
  process.exit(1)
}
fs.rmSync(target,{recursive:true,force:true})
fs.cpSync(source,target,{recursive:true})
console.log('Copied frontend build into desktop/renderer')
