// 统一请求封装
// 自动带 token，401 自动跳登录，统一处理响应格式

function request(url, method = 'GET', data = {}) {
  return new Promise((resolve, reject) => {
    // getApp() 放在函数内部调用，避免模块加载时 app 未初始化
    const app = getApp()
    const baseUrl = (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
    const token = (app && app.globalData && app.globalData.token) || ''

    wx.request({
      url: baseUrl + url,
      method: method,
      data: data,
      header: {
        'Content-Type': 'application/json',
        'Authorization': token ? 'Bearer ' + token : ''
      },
      success(res) {
        // 401 = token 过期，清除并跳转登录
        if (res.statusCode === 401) {
          app.globalData.token = ''
          app.globalData.userInfo = null
          wx.removeStorageSync('token')
          wx.removeStorageSync('userInfo')
          wx.redirectTo({ url: '/pages/login/login' })
          reject(new Error('登录已过期'))
          return
        }
        // 统一响应格式 { code, message, data }
        if (res.data && res.data.code === 200) {
          resolve(res.data.data)
        } else {
          wx.showToast({ title: (res.data && res.data.message) || '请求失败', icon: 'none' })
          reject(new Error((res.data && res.data.message) || '请求失败'))
        }
      },
      fail(err) {
        wx.showToast({ title: '网络错误', icon: 'none' })
        reject(err)
      }
    })
  })
}

module.exports = { request }