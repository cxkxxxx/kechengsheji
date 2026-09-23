// 首页逻辑：获取攻略文章列表（每屏固定 8 条，下拉刷新轮换展示未看过的）
const { request } = require('../../utils/request')

const PAGE = 8 // 每屏固定显示条数

Page({
  data: {
    categories: ['全部', '餐饮', '购物', '生活', '羊毛'],
    currentCategory: '全部',
    articles: [],
    keyword: '',
    filtered: [],
    loading: true,
    refreshing: false
  },

  onLoad() { this.loadArticles() },

  // 初始/切换分类/搜索：加载全量，显示前 8 条
  async loadArticles(force = false) {
    this.setData({ loading: true })
    try {
      await this.fetchList(force)
      this._viewed = {} // 已展示 id 集合（轮换用）
      this._cursor = 0
      this.setData({ filtered: this.pickNext(this.data.keyword), loading: false })
    } catch (e) {
      this.setData({ loading: false, filtered: [] })
      console.error(e)
    }
  },

  // 下拉刷新：轮换展示下一批未看过的 8 条
  onRefresherRefresh() {
    this.setData({ refreshing: true })
    wx.vibrateShort({ type: 'light' })
    setTimeout(() => {
      if (!this._all || !this._all.length) {
        this.loadArticles()
      } else {
        this.setData({ filtered: this.pickNext(this.data.keyword) })
      }
      wx.stopPullDownRefresh && wx.stopPullDownRefresh()
      this.setData({ refreshing: false })
    }, 500) // 让刷新动画有可见过程
  },

  // 从全量中取下一批未看过的 8 条；全部看完则循环
  pickNext(keyword) {
    const all = this._all || []
    const list = all.filter(a =>
      !keyword ||
      (a.title && a.title.indexOf(keyword) >= 0) ||
      (a.category && a.category.indexOf(keyword) >= 0)
    )
    // 未展示的候选
    let unseen = list.filter(a => !this._viewed[a.id])
    // 全部已看过则重置循环
    if (unseen.length === 0) {
      this._viewed = {}
      unseen = list
    }
    // 取下一个滑块（按 cursor 平滑推进，保证顺序稳定）
    const batch = []
    let picked = 0
    const start = this._cursor % Math.max(list.length, 1)
    for (let i = 0; picked < PAGE && i < list.length; i++) {
      const item = list[(start + i) % list.length]
      if (!this._viewed[item.id]) {
        batch.push(item)
        this._viewed[item.id] = true
        picked++
      }
    }
    this._cursor += picked
    return batch
  },

  // 拉取文章列表（缓存到 _all）
  async fetchList(force = false) {
    const cat = this.data.currentCategory === '全部' ? '' : this.data.currentCategory
    const data = await request('/articles?category=' + cat, 'GET', {}, force)
    this._all = data || []
    return this._all
  },

  // 切换分类
  switchCategory(e) {
    this.setData({ currentCategory: e.currentTarget.dataset.cat, filtered: [], loading: true })
    this.loadArticles()
  },

  // 清空搜索词
  clearSearch() {
    this.setData({ keyword: '' })
    this._viewed = {}
    this._cursor = 0
    this.setData({ filtered: this.pickNext('') })
  },

  // 搜索
  onSearch(e) {
    const keyword = e.detail.value
    this.setData({ keyword })
    this._viewed = {}
    this._cursor = 0
    this.setData({ filtered: this.pickNext(keyword) })
  },

  // 跳转文章详情
  goDetail(e) {
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + e.currentTarget.dataset.id })
  }
})
