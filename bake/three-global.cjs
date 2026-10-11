// esbuild 别名目标：让 GLTFExporter 里的 `import … from 'three'` 用页面已有的 window.THREE
// （同一套类，instanceof 判断才成立；也不必再打进第二份 three）
module.exports = window.THREE;
