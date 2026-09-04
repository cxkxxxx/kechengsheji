// 我的页面逻辑
const { request } = require('../../utils/request')

Page({
  data: { user: {}, checkinDays: 0 },

  onShow() {
    this.loadUser()
  },

  async loadUser() {
    try {
      const data = await request('/auth/me')
      this.setData({ user: data })
    } catch (e) {
      // 未登录，跳转登录页
      wx.redirectTo({ url: '/pages/login/login' })
    }
  },

  goCheckin() { wx.switchTab({ url: '/pages/bill/bill' }) },
  goFavorites() { wx.showToast({ title: '开发中', icon: 'none' }) },
  goMyPosts() { wx.showToast({ title: '开发中', icon: 'none' }) },
  goSettings() { wx.showToast({ title: '开发中', icon: 'none' }) }
})
