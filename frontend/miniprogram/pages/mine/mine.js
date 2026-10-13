// 我的页面逻辑
const { request } = require('../../utils/request')
const { formatMoney, fullUrl } = require('../../utils/util')

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
    favTotal: 0,
    myPosts: [],
    postTotal: 0,
    postPublished: 0,
    mySubs: [],
    subTotal: 0,
    subPublished: 0,
    showFav: false,
    showPosts: false,
    showSubs: false,
    loading: true
  },

  // loadMyPosts 依赖 user.id，必须等 loadUser 回来再发，
  // 否则首屏拿到空 id 直接 return，「我的发帖」就永远是空的
  async onShow() {
    await this.loadUser()
    this.loadFavorites()
    this.loadMyPosts()
    this.loadMySubs()
  },

  // 下拉刷新：刷新用户信息 + 收藏 + 我的发帖 + 我的投稿
  async onPullDownRefresh() {
    try {
      await this.loadUser(true)
      await Promise.all([this.loadFavorites(true), this.loadMyPosts(true), this.loadMySubs(true)])
    } finally {
      wx.stopPullDownRefresh()
    }
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
      return true
    } catch (e) {
      this.setData({ loading: false })
      wx.redirectTo({ url: '/pages/login/login' })
      return false
    }
  },

  async toggleFavorites() { this.setData({ showFav: !this.data.showFav }) },

  async toggleMyPosts() { this.setData({ showPosts: !this.data.showPosts }) },

  async loadFavorites(force = false) {
    try {
      const list = await request('/favorites/list', 'GET', {}, force)
      const items = (list || []).map(f => Object.assign({}, f, {
        timeText: briefTime(f.created_at),
        typeLabel: f.target_type === 'post' ? '帖子' : '攻略'
      }))
      this.setData({ favList: items, favTotal: items.length })
    } catch (e) { console.error(e) }
  },

  async loadMyPosts(force = false) {
    const myId = this.data.user.id
    if (!myId) return
    try {
      const data = await request('/posts/mine', 'GET', {}, force) || {}
      const STATUS = { pending: ['审核中', 'chip-warn'], approved: ['已发布', 'chip-ok'], rejected: ['未通过', 'chip-danger'] }
      this.setData({
        myPosts: (data.items || []).map(p => Object.assign({}, p, {
          timeText: briefTime(p.created_at),
          statusText: (STATUS[p.status] || ['', 'chip-grey'])[0],
          statusCls: (STATUS[p.status] || ['', 'chip-grey'])[1]
        })),
        // 数量取服务端 total，不再用「当前渲染出来几条」当总数
        postTotal: data.total || 0,
        postPublished: data.published || 0
      })
    } catch (e) { console.error(e) }
  },

  // 我的投稿（攻略）和我的发帖（社区）是两张表，用户会以为「发帖」包含两者，
  // 所以这里必须单独列一栏，不能只给社区帖
  async loadMySubs(force = false) {
    if (!this.data.user.id) return
    try {
      const data = await request('/articles/mine', 'GET', {}, force) || {}
      const STATUS = { pending: ['审核中', 'chip-warn'], approved: ['已发布', 'chip-ok'], rejected: ['未通过', 'chip-danger'] }
      this.setData({
        mySubs: (data.items || []).map(r => {
          const s = STATUS[r.status] || [r.status || '', 'chip-grey']
          return Object.assign({}, r, { statusText: s[0], statusCls: s[1], coverUrl: fullUrl(r.cover) })
        }),
        subTotal: data.total || 0,
        subPublished: data.published || 0
      })
    } catch (e) { console.error(e) }
  },

  async toggleSubs() { this.setData({ showSubs: !this.data.showSubs }) },

  goArticleCreate() { wx.navigateTo({ url: '/pages/articleCreate/articleCreate' }) },

  goArticleDetail(e) {
    const { id, status } = e.currentTarget.dataset
    if (status !== 'approved') {
      wx.showToast({ title: '这篇还没通过审核，暂不可见', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + id })
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
