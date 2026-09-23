// 我的页面逻辑
const { request } = require('../../utils/request')
const { formatMoney } = require('../../utils/util')

function briefTime(v) {
  const s = String(v || '')
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})/)
  return m ? (m[1] + '-' + m[2] + '-' + m[3]) : s.slice(0, 10)
}

Page({
  data: {
    user: {},
    savedText: '0.00',
    goalText: '未设置',
    favList: [],
    myPosts: [],
    showFav: false,
    showPosts: false,
    loading: true
  },

  onShow() {
    this.loadUser()
    this.loadFavorites()
    this.loadMyPosts()
  },

  // 下拉刷新：刷新用户信息 + 收藏 + 我的发帖
  onPullDownRefresh() {
    Promise.all([
      this.loadUser(true),
      this.loadFavorites(true),
      this.loadMyPosts(true)
    ]).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh())
  },

  async loadUser(force = false) {
    try {
      const data = await request('/auth/me', 'GET', {}, force)
      this.setData({
        user: data || {},
        savedText: formatMoney(data && data.total_saved),
        goalText: data && data.budget_goal ? formatMoney(data.budget_goal) + ' 元/月' : '未设置',
        loading: false
      })
    } catch (e) {
      this.setData({ loading: false })
      wx.redirectTo({ url: '/pages/login/login' })
    }
  },

  async toggleFavorites() { this.setData({ showFav: !this.data.showFav }) },

  async toggleMyPosts() { this.setData({ showPosts: !this.data.showPosts }) },

  async loadFavorites(force = false) {
    try {
      const list = await request('/favorites/list', 'GET', {}, force)
      this.setData({
        favList: (list || []).map(f => Object.assign({}, f, {
          timeText: briefTime(f.created_at),
          typeLabel: f.target_type === 'post' ? '帖子' : '攻略'
        }))
      })
    } catch (e) { console.error(e) }
  },

  async loadMyPosts(force = false) {
    try {
      const allPosts = await request('/posts', 'GET', {}, force)
      const myId = this.data.user.id
      if (!myId) return
      this.setData({
        myPosts: (allPosts || []).filter(p => p.user_id === myId).map(p => Object.assign({}, p, {
          timeText: briefTime(p.created_at)
        }))
      })
    } catch (e) { console.error(e) }
  },

  // 收藏项按类型跳不同详情页（WXML 里不能动态拼 bindtap 的方法名）
  openFavorite(e) {
    const { id, type } = e.currentTarget.dataset
    if (type === 'post') wx.navigateTo({ url: '/pages/postDetail/postDetail?id=' + id })
    else wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + id })
  },

  goPostDetail(e) {
    wx.navigateTo({ url: '/pages/postDetail/postDetail?id=' + e.currentTarget.dataset.id })
  },

  goBill() { wx.switchTab({ url: '/pages/bill/bill' }) },

  goAssistant() { wx.switchTab({ url: '/pages/assistant/assistant' }) },

  goSettings() {
    wx.showToast({ title: '设置功能开发中', icon: 'none' })
  },

  logout() {
    const app = getApp()
    app.globalData.token = ''
    app.globalData.userInfo = null
    wx.removeStorageSync('token')
    wx.removeStorageSync('userInfo')
    wx.redirectTo({ url: '/pages/login/login' })
  }
})
