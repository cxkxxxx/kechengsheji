// 登录页：微信一键登录（服务端配了密钥才显示）+ 昵称密码登录/注册
const { request } = require('../../utils/request')
const app = getApp()

function saveAndGo(data) {
  app.globalData.token = data.token
  app.globalData.userInfo = data.user
  wx.setStorageSync('token', data.token)
  wx.setStorageSync('userInfo', data.user)
  wx.switchTab({ url: '/pages/index/index' })
}

Page({
  data: {
    wxAvailable: false,
    tab: 'login',            // login | register
    nickname: '',
    password: '',
    busy: false,
  },

  async onLoad() {
    // 已有 token 就不该再停在登录页
    if (app.globalData.token) {
      wx.switchTab({ url: '/pages/index/index' })
      return
    }
    try {
      const cfg = await request('/auth/config')
      this.setData({ wxAvailable: !!(cfg && cfg.wx_login) })
    } catch (e) { /* 拿不到就只给密码登录，别把页面卡住 */ }
  },

  onField(e) {
    this.setData({ [e.currentTarget.dataset.field]: e.detail.value })
  },

  switchTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab })
  },

  async handleLogin() {
    if (this.data.busy) return
    const { nickname, password, tab } = this.data
    if (!nickname.trim() || !password) {
      wx.showToast({ title: '请填写昵称和密码', icon: 'none' })
      return
    }
    if (tab === 'register' && password.length < 6) {
      wx.showToast({ title: '密码至少 6 位', icon: 'none' })
      return
    }
    this.setData({ busy: true })
    try {
      const data = await request(tab === 'register' ? '/auth/register' : '/auth/login-password',
                                 'POST', { nickname, password })
      saveAndGo(data)
      wx.showToast({ title: tab === 'register' ? '注册成功' : '欢迎回来', icon: 'success' })
    } catch (e) {
      // request() 已经弹过 toast，这里只负责解除按钮锁
    } finally {
      this.setData({ busy: false })
    }
  },

  // 微信登录：code 一次性，每次都要重新 wx.login 取
  wxLogin() {
    if (this.data.busy) return
    this.setData({ busy: true })
    const that = this
    wx.login({
      async success(res) {
        if (!res.code) {
          that.setData({ busy: false })
          wx.showToast({ title: '没拿到微信凭证，请重试', icon: 'none' })
          return
        }
        try {
          saveAndGo(await request('/auth/login', 'POST', { code: res.code }))
        } catch (e) {
          // 后端会回具体原因（AppID 不对 / code 失效），照原样提示
        } finally {
          that.setData({ busy: false })
        }
      },
      fail() {
        that.setData({ busy: false })
        wx.showToast({ title: '微信登录失败', icon: 'none' })
      },
    })
  },
})
