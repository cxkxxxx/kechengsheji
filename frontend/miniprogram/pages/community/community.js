// 社区页逻辑：内容优先的信息流（每屏固定 8 条，下拉刷新轮换展示未看过的）
// 标签筛选条从已有帖子的标签里统计出来，有真数据才显示，不做假分类
const { request } = require('../../utils/request')
const { imageGrid, fullUrl } = require('../../utils/util')

const PAGE = 8
const MAX_TAGS = 6   // 筛选条最多放 6 个标签，多的让位给内容

// 后端给的是 ISO 时间串，列表只需要「月-日 时:分」
function briefTime(v) {
  const s = String(v || '')
  const m = s.match(/(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/)
  if (!m) return s.slice(0, 10)
  const now = new Date()
  const sameYear = +m[1] === now.getFullYear()
  return (sameYear ? '' : m[1] + '年') + (+m[2]) + '月' + (+m[3]) + '日 ' + m[4] + ':' + m[5]
}

// tags 存的是逗号分隔字符串
function briefTags(v) {
  if (!v) return []
  return String(v).split(/[,，]/).map(t => t.trim()).filter(Boolean).slice(0, 3)
}

function decorate(p) {
  // 卡片上最多铺 4 张（第 4 张压一层「+N」），完整九宫格留给详情页
  const grid = imageGrid(p.images, 9)
  const shown = grid.list.slice(0, 4)
  return Object.assign({}, p, {
    timeText: briefTime(p.created_at),
    tagList: briefTags(p.tags),
    // 作者头像和昵称由 /posts join User 带出来；头像存的是 /static/ 相对路径
    author: p.author || '省钱用户',
    avatarUrl: p.author_avatar ? fullUrl(p.author_avatar) : '',
    gridCls: 'imgs imgs-' + shown.length,
    gridShown: shown,
    gridMore: grid.n > 4 ? grid.n - 4 : 0,
  })
}

// 按当前选中标签过滤（操作的是未装饰的原始数据，tags 是逗号分隔字符串）
function matchTag(p, tag) {
  if (!tag || tag === '全部') return true
  return briefTags(p.tags).indexOf(tag) >= 0
}

Page({
  data: { posts: [], tags: ['全部'], currentTag: '全部', refreshing: false, loading: true },

  onLoad() { this.loadPosts() },
  onShow() { this.loadPosts() },

  // 初始/返回：加载全量并显示前 8 条（保留已轮换的状态）
  async loadPosts(force = false) {
    try {
      const data = await request('/posts', 'GET', {}, force)
      if (Array.isArray(data) && data.length) {
        this._all = data
        this._applyTag(this.data.currentTag, false)
      } else if (!this._all) {
        this._all = []
        this._viewed = {}
        this._cursor = 0
        this.setData({ posts: [], tags: ['全部'], loading: false })
      } else {
        this.setData({ loading: false })
      }
    } catch (e) {
      this.setData({ loading: false })
      console.error(e)
    }
  },

  // 根据标签重建候选池并轮换出一屏；reset=true 表示用户切了标签，从头轮换
  _applyTag(tag, reset) {
    const all = this._all || []
    // 标签条：全部 + 出现次数最多的前几个标签（有真内容才显示出来）
    const freq = {}
    all.forEach(p => briefTags(p.tags).forEach(t => { freq[t] = (freq[t] || 0) + 1 }))
    const hot = Object.keys(freq).sort((a, b) => freq[b] - freq[a]).slice(0, MAX_TAGS)
    this._pool = all.filter(p => matchTag(p, tag))
    if (reset) { this._viewed = {}; this._cursor = 0 }
    else if (!this._viewed) { this._viewed = {}; this._cursor = 0 }
    const update = { tags: ['全部'].concat(hot), currentTag: tag, loading: false }
    if (this.data.posts.length === 0 || reset) update.posts = this.pickNext().map(decorate)
    this.setData(update)
  },

  // 点标签：切筛选并重出一屏
  pickTag(e) {
    const tag = e.currentTarget.dataset.tag
    if (tag === this.data.currentTag) return
    this._applyTag(tag, true)
  },

  // 下拉刷新：轮换下一批未看过的 8 条
  onRefresherRefresh() {
    this.setData({ refreshing: true })
    wx.vibrateShort({ type: 'light' })
    setTimeout(() => {
      if (this._pool && this._pool.length) {
        this.setData({ posts: this.pickNext().map(decorate) })
      } else {
        this.loadPosts()
      }
      this.setData({ refreshing: false })
    }, 500)
  },

  pickNext() {
    const all = this._pool || []
    let unseen = all.filter(p => !this._viewed[p.id])
    if (unseen.length === 0) { this._viewed = {}; unseen = all }
    const batch = []
    const start = this._cursor % Math.max(all.length, 1)
    let picked = 0
    for (let i = 0; picked < PAGE && i < all.length; i++) {
      const item = all[(start + i) % all.length]
      if (!this._viewed[item.id]) {
        batch.push(item)
        this._viewed[item.id] = true
        picked++
      }
    }
    this._cursor += picked
    return batch
  },

  goPostDetail(e) {
    wx.navigateTo({ url: '/pages/postDetail/postDetail?id=' + e.currentTarget.dataset.id })
  },

  // 点赞/取消点赞（catchtap 阻止冒泡）
  async likePost(e) {
    const id = e.currentTarget.dataset.id
    try {
      const res = await request('/posts/' + id + '/like', 'POST')
      // _pool / _all / 当前屏三处都要同步，不然轮换回来数字又变回去
      const apply = list => (list || []).map(p => {
        if (p.id == id) { p.likes = res.likes; p.liked = res.liked }
        return p
      })
      this._pool = apply(this._pool)
      this._all = apply(this._all)
      this.setData({ posts: apply(this.data.posts) })
    } catch (err) { console.error(err) }
  },

  goCreatePost() {
    wx.navigateTo({ url: '/pages/postCreate/postCreate' })
  },

  // 点帖子里的图全屏预览，左右滑动看这一组的其它图
  previewPostImage(e) {
    const urls = e.currentTarget.dataset.urls || []
    if (!urls.length) return
    wx.previewImage({ urls, current: e.currentTarget.dataset.current || urls[0] })
  }
})
