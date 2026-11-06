// 攻略列表页：搜索 + 分类筛选 + 完整列表（从首页迁来，首页只留精选）
const { request } = require('../../utils/request')
const { fullUrl } = require('../../utils/util')

const BASE_CATEGORIES = ['全部', '餐饮', '羊毛', '购物', '生活', '账单']
const BILL_GUIDE_RE = /(账单|记账|预算|支出|消费|超支|花销|月光)/

Page({
  data: {
    categories: BASE_CATEGORIES,
    currentCategory: '全部',
    keyword: '',
    filtered: [],
    loading: true
  },

  onLoad(options) {
    if (options && options.category) {
      this.setData({ currentCategory: options.category })
    }
    this.loadCategories()
    this.loadArticles()
  },

  onPullDownRefresh() {
    this.loadArticles(true).then(() => wx.stopPullDownRefresh()).catch(() => wx.stopPullDownRefresh())
  },

  async loadCategories() {
    try {
      const cats = await request('/articles/categories')
      if (Array.isArray(cats) && cats.length) {
        const categories = BASE_CATEGORIES.concat(cats.filter(cat => BASE_CATEGORIES.indexOf(cat) < 0))
        this.setData({ categories })
      }
    } catch (e) { /* 拿不到就用默认清单 */ }
  },

  async loadArticles(force = false) {
    this.setData({ loading: true })
    try {
      const cat = this.data.currentCategory === '全部' || this.data.currentCategory === '账单'
        ? '' : this.data.currentCategory
      const data = await request('/articles?category=' + cat, 'GET', {}, force)
      this._all = (data || []).map(a => Object.assign({}, a, { coverUrl: fullUrl(a.cover) }))
      this.setData({ filtered: this.applyKeyword(this.data.keyword), loading: false })
    } catch (e) {
      this.setData({ loading: false, filtered: [] })
      console.error(e)
    }
  },

  applyKeyword(keyword) {
    const list = this._all || []
    const category = this.data.currentCategory
    return list.filter(a => {
      const searchable = (a.title || '') + ' ' + (a.category || '') + ' ' + (a.content || '')
      const matchesCategory = category === '全部' ||
        (category === '账单' ? BILL_GUIDE_RE.test(searchable) : a.category === category)
      return matchesCategory && (!keyword || searchable.indexOf(keyword) >= 0)
    })
  },

  switchCategory(e) {
    this.setData({ currentCategory: e.currentTarget.dataset.cat, filtered: [], loading: true })
    this.loadArticles()
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value, filtered: this.applyKeyword(e.detail.value) })
  },

  clearSearch() {
    this.setData({ keyword: '', filtered: this.applyKeyword('') })
  },

  goDetail(e) {
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + e.currentTarget.dataset.id })
  },

  goCreate() {
    wx.navigateTo({ url: '/pages/articleCreate/articleCreate' })
  },

  // 卡片上的收藏入口：切换后就地更新红心，不用整页刷新
  async toggleFav(e) {
    const id = parseInt(e.currentTarget.dataset.id, 10)
    const idx = this.data.filtered.findIndex(a => a.id === id)
    if (idx < 0) return
    try {
      const r = await request('/favorites/toggle?target_type=article&target_id=' + id, 'POST')
      this.setData({ ['filtered[' + idx + '].liked']: !!(r && r.favorited) })
      wx.showToast({ title: r && r.favorited ? '已收藏' : '已取消收藏', icon: 'none' })
    } catch (err) { /* 401 时 request 会跳登录 */ }
  }
})
