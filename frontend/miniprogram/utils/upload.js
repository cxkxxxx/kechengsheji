// 图片选择 + 上传。社区发帖和攻略投稿共用，两边限制口径必须一致。
const MAX_MB = 2

function base() {
  const app = getApp()
  return (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
}

function token() {
  const app = getApp()
  return (app && app.globalData && app.globalData.token) || ''
}

function toast(title) {
  wx.showToast({ title: title, icon: 'none' })
}

// wx.chooseMedia 只在较新基础库上有；老版本退回 chooseImage，否则低版本用户点了没反应
function choose(count) {
  return new Promise((resolve, reject) => {
    const keep = (files) => {
      const ok = [], skipped = []
      files.forEach(f => {
        // size 拿不到时（老基础库的 chooseImage）先放行，交给后端的 2MB 校验拦
        if (typeof f.size === 'number' && f.size > MAX_MB * 1024 * 1024) skipped.push(1)
        else ok.push(f.path)
      })
      if (skipped.length) toast('有 ' + skipped.length + ' 张超过 ' + MAX_MB + 'MB，已跳过')
      resolve(ok)
    }
    if (wx.chooseMedia) {
      wx.chooseMedia({
        count, mediaType: ['image'], sizeType: ['compressed'],
        success: (res) => keep((res.tempFiles || []).map(f => ({ path: f.tempFilePath, size: f.size }))),
        fail: reject,
      })
    } else {
      wx.chooseImage({
        count, sizeType: ['compressed'],
        success: (res) => keep((res.tempFilePaths || []).map(p => ({ path: p, size: null }))),
        fail: reject,
      })
    }
  })
}

function uploadOne(filePath) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: base() + '/upload/image',
      filePath,
      name: 'file',                       // 后端 UploadFile 参数名
      header: { Authorization: token() ? 'Bearer ' + token() : '' },
      success(res) {
        let body = {}
        try { body = JSON.parse(res.data) } catch (e) { /* 非 JSON 一般是网关错误页 */ }
        if (res.statusCode === 200 && body.code === 200) {
          resolve(body.data.url)
        } else {
          // 后端校验失败走 HTTPException，文案在 detail 而不是 message
          reject(new Error(body.detail || body.message || '上传失败'))
        }
      },
      fail: () => reject(new Error('网络错误，上传失败')),
    })
  })
}

/**
 * 选图并逐张上传。
 * @param {number} remain 还能选几张
 * @param {(done:number, total:number)=>void} onProgress 上传进度回调
 * @returns {Promise<string[]>} 上传成功的 /static/ 地址列表
 */
async function pickAndUpload(remain, onProgress) {
  if (remain <= 0) {
    toast('图片已经选满了')
    return []
  }
  let paths
  try {
    paths = await choose(remain)
  } catch (e) {
    return []                              // 用户取消，不当错误
  }
  const urls = []
  for (let i = 0; i < paths.length; i++) {
    if (onProgress) onProgress(i, paths.length)
    try {
      urls.push(await uploadOne(paths[i]))
    } catch (err) {
      toast(err.message || '有图片上传失败')   // 一张失败不中断其余
    }
  }
  if (onProgress) onProgress(paths.length, paths.length)
  return urls
}

module.exports = { pickAndUpload, MAX_MB }
