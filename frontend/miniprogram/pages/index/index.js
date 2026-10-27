// 首页逻辑：获取攻略文章列表（每屏固定 8 条，下拉刷新轮换展示未看过的）
const { request } = require('../../utils/request')
const { fullUrl } = require('../../utils/util')

const PAGE = 8 // 每屏固定显示条数
const BASE_CATEGORIES = ['全部', '餐饮', '羊毛', '购物', '生活', '账单']
const BILL_GUIDE_RE = /(账单|记账|预算|支出|消费|超支|花销|月光)/

Page({
  data: {
    categories: BASE_CATEGORIES,
    currentCategory: '全部',
    articles: [],
    keyword: '',
    filtered: [],
    loading: true,
    refreshing: false
  },

  onLoad() {
    this.loadCategories()
    this.loadArticles()
  },

  // 分类跟着已有内容走：写死一份清单的话，新分类的攻略永远筛不出来
  async loadCategories() {
    try {
      const cats = await request('/articles/categories')
      if (Array.isArray(cats) && cats.length) {
        const categories = BASE_CATEGORIES.concat(cats.filter(cat => BASE_CATEGORIES.indexOf(cat) < 0))
        this.setData({ categories })
      }
    } catch (e) { /* 拿不到就用默认清单 */ }
  },

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
    this._viewed = this._viewed || {}
    this._cursor = this._cursor || 0
    const all = this._all || []
    const category = this.data.currentCategory
    const list = all.filter(a => {
      const searchable = (a.title || '') + ' ' + (a.category || '') + ' ' + (a.content || '')
      const matchesCategory = category === '全部' ||
        (category === '账单' ? BILL_GUIDE_RE.test(searchable) : a.category === category)
      return matchesCategory && (!keyword || searchable.indexOf(keyword) >= 0)
    })
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
    const cat = this.data.currentCategory === '全部' || this.data.currentCategory === '账单'
      ? '' : this.data.currentCategory
    const data = await request('/articles?category=' + cat, 'GET', {}, force)
    // cover 存的是 /static/ 相对路径，<image> 要绝对地址
    this._all = (data || []).map(a => Object.assign({}, a, { coverUrl: fullUrl(a.cover) }))
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
  },

  goCreate() {
    wx.navigateTo({ url: '/pages/articleCreate/articleCreate' })
  },

  // 问 AI：带着当前分类跳优惠情报员，省得用户再打一遍字
  goAsk() {
    const cat = this.data.currentCategory === '全部' ? '' : this.data.currentCategory
    getApp().globalData.pendingAsk = {
      agent: 'coupon',
      question: (cat ? cat + '方面' : '') + '最近有什么值得薅的羊毛和省钱攻略？',
    }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  },

  // 快捷入口：比价和账单都是独立页面/标签页
  goPrice() {
    wx.navigateTo({ url: '/pages/price/price' })
  },

  goBill() {
    wx.switchTab({ url: '/pages/bill/bill' })
  }
})
