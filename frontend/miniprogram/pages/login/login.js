// 登录页逻辑
const { request } = require('../../utils/request')
const app = getApp()

Page({
  handleLogin() {
    wx.login({
      success: async (res) => {
        if (res.code) {
          try {
            const data = await request('/auth/login', 'POST', {
              code: res.code,
              nickname: '省钱达人',
              avatar: ''
            })
            // 保存 token 和用户信息（持久化到本地存储）
            app.globalData.token = data.token
            app.globalData.userInfo = data.user
            wx.setStorageSync('token', data.token)
            wx.setStorageSync('userInfo', data.user)
            wx.switchTab({ url: '/pages/index/index' })
          } catch (e) {
            wx.showToast({ title: '登录失败', icon: 'none' })
          }
        }
      }
    })
  }
})