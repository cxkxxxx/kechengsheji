// 统一请求封装
// 自动带 token，401 自动跳登录，统一处理响应格式
// GET 请求带 2 秒内存缓存：切换 tab/页面时秒开不白屏，下拉刷新可强制更新

// 内存缓存 { key: { time, data } }
const cache = {}
const CACHE_TTL = 2000 // 2 秒

function request(url, method = 'GET', data = {}, force = false) {
  return new Promise((resolve, reject) => {
    const app = getApp()
    const baseUrl = (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
    const token = (app && app.globalData && app.globalData.token) || ''

    const cacheKey = method.toUpperCase() + '|' + url + '|' + JSON.stringify(data || {})
    if (method.toUpperCase() === 'GET' && !force) {
      const hit = cache[cacheKey]
      if (hit && Date.now() - hit.time < CACHE_TTL) {
        resolve(hit.data)
        return
      }
    }

    // DELETE/HEAD 不能带请求体：uvicorn 收到带 body 的 DELETE 会直接 400
    const noBody = method === 'DELETE' || method === 'HEAD'
    wx.request({
      url: baseUrl + url,
      method: method,
      data: noBody ? undefined : data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : ''
      },
      success(res) {
        // 登录接口自己的 401 是「昵称或密码不对」，不是登录态过期。
        // 当成过期会把用户踢回登录页并提示重新登录，密码错了永远改不掉。
        const isAuthCall = url.indexOf('/auth/login') === 0 || url.indexOf('/auth/register') === 0
        if (res.statusCode === 401 && !isAuthCall) {
          app.globalData.token = ''
          app.globalData.userInfo = null
          wx.removeStorageSync('token')
          wx.removeStorageSync('userInfo')
          wx.redirectTo({ url: '/pages/login/login' })
          reject(new Error('登录已过期'))
          return
        }
        if (res.data && res.data.code === 200) {
          if (method.toUpperCase() === 'GET') {
            cache[cacheKey] = { time: Date.now(), data: res.data.data }
          }
          resolve(res.data.data)
        } else {
          const hit = cache[cacheKey]
          if (hit) { resolve(hit.data); return }
          const msg = (res.data && (res.data.message || res.data.detail)) || '请求失败'
          wx.showToast({ title: msg, icon: 'none' })
          reject(new Error(msg))
        }
      },
      fail(err) {
        const hit = cache[cacheKey]
        if (hit) { resolve(hit.data); return }
        wx.showToast({ title: '网络错误', icon: 'none' })
        reject(err)
      }
    })
  })
}

module.exports = { request }
