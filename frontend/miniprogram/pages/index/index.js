// 首页逻辑：获取攻略文章列表
const { request } = require('../../utils/request')

Page({
  data: {
    categories: ['全部', '餐饮', '购物', '生活', '羊毛'],
    currentCategory: '全部',
    articles: []
  },

  onLoad() {
    this.loadArticles()
  },

  // 加载文章列表
  async loadArticles() {
    try {
      const cat = this.data.currentCategory === '全部' ? '' : this.data.currentCategory
      const data = await request('/articles?category=' + cat)
      this.setData({ articles: data || [] })
    } catch (e) { console.error(e) }
  },

  // 切换分类
  switchCategory(e) {
    this.setData({ currentCategory: e.currentTarget.dataset.cat })
    this.loadArticles()
  },

  // 跳转文章详情
  goDetail(e) {
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + e.currentTarget.dataset.id })
  },

  onSearch(e) {
    // TODO: 搜索功能
  }
})
