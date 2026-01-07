<template>
  <!-- TEMP: show crash instead of blank white -->
  <div v-if="fatalError" class="p-3 m-3 rounded border border-red-300 bg-red-50 text-red-800 text-sm">
    <div class="font-semibold mb-1">Something crashed on this page.</div>
    <pre class="whitespace-pre-wrap text-xs">{{ fatalError }}</pre>
  </div>

  <LayoutHeader>
    <template #left-header>
      <ViewBreadcrumbs v-model="viewControls" routeName="Leads" />
    </template>

    <template #right-header>
      <CustomActions
        v-if="leadsListView?.customListActions"
        :actions="leadsListView.customListActions"
      />
      <Button variant="solid" :label="__('Create')" @click="showLeadModal = true">
        <template #prefix><FeatherIcon name="plus" class="h-4" /></template>
      </Button>
    </template>
  </LayoutHeader>

  <!-- Quick Filters Bar -->
  <QuickFiltersBar
    v-model="ui"
    :status-list="statusList"
    :project-list="projectList"
    :owner-list="ownerList"
    status-field="status"
    :project-field="PROJECT_FIELD"
    owner-field="lead_owner"
    :last-contact-field="LAST_CONTACT_FIELD.fieldname"
    @filters-change="applyFilters"
    @like-change="applyLike"
    @open-all="() => { showFilters = true }"
  />

  <!-- Drawer (All Filters) -->
  <AllFiltersDrawer
    v-if="SHOW_LEAD_FILTERS"
    v-model:show="showFilters"
    :model-value="ui"
    :status-list="statusList"
    :project-list="projectList"
    :location-list="locationList"
    :source-list="sourceList"
    :origin-list="originList"
    :type-list="typeList"
    @apply="applyFiltersFromPanel"
    @clear="clearDrawer"
  />

  <!-- ViewControls manages list/group_by/kanban data loading -->
  <ViewControls
    ref="viewControls"
    v-model="leads"
    v-model:loadMore="loadMore"
    v-model:resizeColumn="triggerResize"
    v-model:updatedPageCount="updatedPageCount"
    doctype="CRM Lead"
    :options="{ allowedViews: ['list', 'group_by', 'kanban'], disablePersistence: false }"
  />

  <!-- Kanban View -->
  <KanbanView
    v-if="route.params.viewType == 'kanban'"
    v-model="leads"
    :options="{
      getRoute: (row) => ({
        name: 'Lead',
        params: { leadId: row.name },
        query: { view: route.query.view, viewType: route.params.viewType },
      }),
      onNewClick: (column) => onNewClick(column),
    }"
    @update="(data) => viewControls.updateKanbanSettings(data)"
    @loadMore="(columnName) => viewControls.loadMoreKanban(columnName)"
  >
    <template #title="{ titleField, itemName }">
      <div class="flex items-center gap-2">
        <div v-if="titleField === 'status'">
          <IndicatorIcon :class="getRow(itemName, titleField).color" />
        </div>

        <div
          v-else-if="titleField === 'organization' && getRow(itemName, titleField).label"
        >
          <Avatar
            :image="getRow(itemName, titleField).logo"
            :label="getRow(itemName, titleField).label"
            size="sm"
          />
        </div>

        <div
          v-else-if="titleField === 'lead_name' && getRow(itemName, titleField).label"
        >
          <Avatar
            :image="getRow(itemName, titleField).image"
            :label="getRow(itemName, titleField).image_label"
            size="sm"
          />
        </div>

        <div
          v-else-if="titleField === 'lead_owner' && getRow(itemName, titleField).full_name"
        >
          <Avatar
            :image="getRow(itemName, titleField).user_image"
            :label="getRow(itemName, titleField).full_name"
            size="sm"
          />
        </div>

        <!-- date-ish fields -->
        <div
          v-if="[
              'modified',
              'creation',
              'first_response_time',
              'first_responded_on',
              'response_by',
            ].includes(titleField)"
          class="truncate text-base"
        >
          <Tooltip :text="getRow(itemName, titleField).label">
            <div>{{ getRow(itemName, titleField).timeAgo }}</div>
          </Tooltip>
        </div>

        <div v-else-if="titleField === 'sla_status'" class="truncate text-base">
          <Badge
            v-if="getRow(itemName, titleField).value"
            :variant="'subtle'"
            :theme="getRow(itemName, titleField).color"
            size="md"
            :label="getRow(itemName, titleField).value"
          />
        </div>

        <div v-else-if="getRow(itemName, titleField).label" class="truncate text-base">
          {{ getRow(itemName, titleField).label }}
        </div>

        <div class="text-ink-gray-4" v-else>{{ __('No Title') }}</div>
      </div>
    </template>

    <template #fields="{ fieldName, itemName }">
      <div v-if="getRow(itemName, fieldName).label" class="truncate flex items-center gap-2">
        <div v-if="fieldName === 'status'">
          <IndicatorIcon :class="getRow(itemName, fieldName).color" />
        </div>

        <div
          v-else-if="fieldName === 'organization' && getRow(itemName, fieldName).label"
        >
          <Avatar
            :image="getRow(itemName, fieldName).logo"
            :label="getRow(itemName, fieldName).label"
            size="xs"
          />
        </div>

        <div v-else-if="fieldName === 'lead_name'">
          <Avatar
            v-if="getRow(itemName, fieldName).label"
            :image="getRow(itemName, fieldName).image"
            :label="getRow(itemName, fieldName).image_label"
            size="xs"
          />
        </div>

        <div v-else-if="fieldName === 'lead_owner'">
          <Avatar
            v-if="getRow(itemName, fieldName).full_name"
            :image="getRow(itemName, fieldName).user_image"
            :label="getRow(itemName, fieldName).full_name"
            size="xs"
          />
        </div>

        <!-- date-ish fields -->
        <div
          v-if="[
              'modified',
              'creation',
              'first_response_time',
              'first_responded_on',
              'response_by',
            ].includes(fieldName)"
          class="truncate text-base"
        >
          <Tooltip :text="getRow(itemName, fieldName).label">
            <div>{{ getRow(itemName, fieldName).timeAgo }}</div>
          </Tooltip>
        </div>

        <div v-else-if="fieldName === 'sla_status'" class="truncate text-base">
          <Badge
            v-if="getRow(itemName, fieldName).value"
            :variant="'subtle'"
            :theme="getRow(itemName, fieldName).color"
            size="md"
            :label="getRow(itemName, fieldName).value"
          />
        </div>

        <div v-else-if="fieldName === '_assign'" class="flex items-center">
          <MultipleAvatar :avatars="getRow(itemName, fieldName).label" size="xs" />
        </div>

        <div class="truncate text-base" v-else>
          {{ getRow(itemName, fieldName).label }}
        </div>
      </div>
    </template>

    <template #actions="{ itemName }">
      <div class="flex gap-2 items-center justify-between">
        <div class="text-ink-gray-5 flex items-center gap-1.5">
          <EmailAtIcon class="h-4 w-4" />
          <span v-if="getRow(itemName, '_email_count').label">
            {{ getRow(itemName, '_email_count').label }}
          </span>
          <span class="text-3xl leading-[0]"> · </span>

          <NoteIcon class="h-4 w-4" />
          <span v-if="getRow(itemName, '_note_count').label">
            {{ getRow(itemName, '_note_count').label }}
          </span>
            <span class="text-3xl leading-[0]"> · </span>

          <TaskIcon class="h-4 w-4" />
          <span v-if="getRow(itemName, '_task_count').label">
            {{ getRow(itemName, '_task_count').label }}
          </span>
          <span class="text-3xl leading-[0]"> · </span>

          <CommentIcon class="h-4 w-4" />
          <span v-if="getRow(itemName, '_comment_count').label">
            {{ getRow(itemName, '_comment_count').label }}
          </span>
        </div>

        <Dropdown
          class="flex items-center gap-2"
          :options="actions(itemName)"
          variant="ghost"
          @click.stop.prevent
        >
          <Button icon="plus" variant="ghost" />
        </Dropdown>
      </div>
    </template>
  </KanbanView>

  <!-- List View -->
  <LeadsListView
    ref="leadsListView"
    v-else-if="sessionReady && leads.data && rows.length"
    v-model="leads.data.page_length_count"
    v-model:list="leads"
    :rows="rows"
    :columns="columnsForList || leads.data.columns"
    :options="{
      showTooltip: false,
      resizeColumn: true,
      rowCount: leads.data.row_count,
      totalCount: leads.data.total_count,
    }"
    @loadMore="() => loadMore++"
    @columnWidthUpdated="() => triggerResize++"
    @updatePageCount="(count) => (updatedPageCount = count)"
    @applyFilter="(data) => viewControls.applyFilter(data)"
    @applyLikeFilter="(data) => viewControls.applyLikeFilter(data)"
    @likeDoc="(data) => viewControls.likeDoc(data)"
    @selectionsChanged="(selections) => viewControls.updateSelections(selections)"
  />

  <!-- Empty state -->
  <div v-else-if="sessionReady && leads.data" class="flex h-full items-center justify-center">
    <div class="flex flex-col items-center gap-3 text-xl font-medium text-ink-gray-4">
      <LeadsIcon class="h-10 w-10" />
      <span>{{ __('No {0} Found', [__('Leads')]) }}</span>
      <Button :label="__('Create')" @click="showLeadModal = true">
        <template #prefix><FeatherIcon name="plus" class="h-4" /></template>
      </Button>
    </div>
  </div>

  <!-- Modals -->
  <LeadModal v-if="showLeadModal" v-model="showLeadModal" :defaults="defaults" />
  <NoteModal v-if="showNoteModal" v-model="showNoteModal" :note="note" doctype="CRM Lead" :doc="docname" />
  <TaskModal v-if="showTaskModal" v-model="showTaskModal" :task="task" doctype="CRM Lead" :doc="docname" />
</template>

<script setup>
const SHOW_LEAD_FILTERS = true

import ViewBreadcrumbs from '@/components/ViewBreadcrumbs.vue'
import MultipleAvatar from '@/components/MultipleAvatar.vue'
import CustomActions from '@/components/CustomActions.vue'
import EmailAtIcon from '@/components/Icons/EmailAtIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import NoteIcon from '@/components/Icons/NoteIcon.vue'
import TaskIcon from '@/components/Icons/TaskIcon.vue'
import CommentIcon from '@/components/Icons/CommentIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import LeadsIcon from '@/components/Icons/LeadsIcon.vue'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LeadsListView from '@/components/ListViews/LeadsListView.vue'
import KanbanView from '@/components/Kanban/KanbanView.vue'
import LeadModal from '@/components/Modals/LeadModal.vue'
import NoteModal from '@/components/Modals/NoteModal.vue'
import TaskModal from '@/components/Modals/TaskModal.vue'
import ViewControls from '@/components/ViewControls.vue'
import AllFiltersDrawer from '@/components/FcrmFilters/AllFiltersDrawer.vue'
import QuickFiltersBar from '@/components/FcrmFilters/QuickFiltersBar.vue'

import { getMeta } from '@/stores/meta'
import { globalStore } from '@/stores/global'
import { usersStore } from '@/stores/users'
import { statusesStore } from '@/stores/statuses'
import { callEnabled } from '@/composables/settings'
import { formatDate, timeAgo, website, formatTime } from '@/utils'
import { Avatar, Tooltip, Dropdown, Button, FeatherIcon, Badge } from 'frappe-ui'

import { useRoute, onBeforeRouteUpdate } from 'vue-router'
import { ref, computed, reactive, h, watch, onMounted, onActivated } from 'vue'
import { useDebounceFn } from '@vueuse/core'

/* ---------- session + routing ---------- */
const sessionReady = ref(false)
const route = useRoute()
const leadsListView = ref(null)
const showLeadModal = ref(false)
const defaults = reactive({})
const leads = ref({})
const loadMore = ref(1)
const triggerResize = ref(1)
const updatedPageCount = ref(20)
const viewControls = ref(null)
const delayedMap = ref({})
const MAX_DELAYED_BATCH = 200
let lastDelayedNamesKey = ''

/* seen caches */
const seenProjects = ref([])
const seenStatuses = ref([])
const seenLocations = ref([])
const seenSources = ref([])
const seenOrigins = ref([])
const seenTypes = ref([])
const seenStages = ref([])

/* authoritative catalogs loaded once */
const fullProjectCatalog = ref([])
const fullLocationCatalog = ref([])
const fullSourceCatalog = ref([])
const fullOriginCatalog = ref([])
const fullTypeCatalog = ref([])
const fullStageCatalog = ref([])

const SOURCE_FIELD = computed(() => {
  if (getLeadFieldMeta('lead_source')) return 'lead_source'
  if (getLeadFieldMeta('source')) return 'source'
  return 'lead_source'
})

// --- safe frappe.call wrapper ------------------------------------------------
async function safeFrappeCall(opts = {}) {
  try {
    if (window?.frappe && typeof window.frappe.call === 'function') {
      return await window.frappe.call(opts)
    }
    const method = String(opts.method || '')
    const args = opts.args || {}
    const url = `/api/method/${method}`
    const headers = { 'Content-Type': 'application/json' }
    const token = (window?.frappe && window.frappe.csrf_token) ? window.frappe.csrf_token : ''
    if (token) headers['X-Frappe-CSRF-Token'] = token

    const res = await fetch(url, {
      method: 'POST',
      credentials: 'include',
      headers,
      body: JSON.stringify(args),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(json?.exc || res.statusText || 'Request failed')
    return { message: json.message ?? json }
  } catch (e) {
    throw e
  }
}

/* ---------- ensure we're logged in ---------- */
async function ensureSession() {
  if (!window.frappe?.session?.user || window.frappe.session.user === 'Guest') {
    try {
      await window.frappe.call({ method: 'frappe.client.get_logged_user' })
    } catch {}
  }
}

function firstKey(obj, keys, fallback = null) {
  for (const k of keys) {
    if (obj[k] !== undefined && obj[k] !== '') return obj[k]
  }
  return fallback
}

/* ---------- Meta helpers (CRM Lead) ---------- */
const { getFields: getLeadFields, getFormattedPercent, getFormattedFloat, getFormattedCurrency } = getMeta('CRM Lead')

function getLeadFieldMeta(fieldname) {
  const arr = getLeadFields() || []
  return arr.find((f) => f.fieldname === fieldname) || null
}

function norm(strs = []) {
  const out = []
  const seen = new Set()
  strs.forEach((s) => {
    const val = (s ?? '').toString().trim()
    if (!val || seen.has(val)) return
    seen.add(val)
    out.push({ label: val, value: val })
  })
  return out
}

/* Select options from meta (newline-separated) */
function optionsFromSelect(fieldname) {
  const f = getLeadFieldMeta(fieldname)
  if (!f) return []
  if ((f.fieldtype || '').toLowerCase() !== 'select') return []
  const raw = (f.options || '')
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
  return norm(raw)
}

/* values seen in the current rows */
function seenFromRows(fieldname) {
  const vals = new Set()
  ;(rows.value || []).forEach((r) => {
    const cell = r[fieldname]
    const v = cell?.value ?? cell?.label ?? cell
    if (v) vals.add(v)
  })
  return norm([...vals])
}

/* ---------- Projects catalog ---------- */
async function fetchProjectsFrom(doctype) {
  try {
    const res = await safeFrappeCall({
      method: 'frappe.client.get_list',
      args: {
        doctype,
        fields: ['name'],
        limit_page_length: 500,
        order_by: 'modified desc'
      }
    })
    const arr = Array.isArray(res.message) ? res.message : []
    return arr.map((r) => ({ value: r.name, label: r.name }))
  } catch (e) {
    console.warn(`fetchProjectsFrom(${doctype}) failed`, e)
    return []
  }
}

async function fetchDistinctLeadProjects() {
  try {
    const res = await safeFrappeCall({
      method: 'frappe.client.get_list',
      args: {
        doctype: 'CRM Lead',
        fields: ['distinct project as name'],
        filters: [['project', '!=', '']],
        limit_page_length: 500,
        order_by: 'project asc'
      }
    })
    const rows = Array.isArray(res.message) ? res.message : []
    return rows
      .map((r) => (r.name || '').trim())
      .filter(Boolean)
      .map((v) => ({ label: v, value: v }))
  } catch (e) {
    console.warn('distinct projects fallback failed', e)
    return []
  }
}

async function loadProjectsCatalog() {
  let list = await fetchProjectsFrom('Real Estate Project')
  if (!list.length) list = await fetchProjectsFrom('Project')
  if (!list.length) list = await fetchDistinctLeadProjects()

  const merged = new Map()
  list.forEach((p) => merged.set(p.value, p))
  seenFromRows('project').forEach((p) => {
    if (!merged.has(p.value)) merged.set(p.value, p)
  })
  fullProjectCatalog.value = Array.from(merged.values())
}

/* ---------- Simple catalogs from meta + rows ---------- */
function loadSimpleCatalog(fieldname, targetRef) {
  const fromMeta = optionsFromSelect(fieldname)
  const merged = new Map()
  fromMeta.forEach((o) => merged.set(o.value, o))
  seenFromRows(fieldname).forEach((o) => {
    if (!merged.has(o.value)) merged.set(o.value, o)
  })
  targetRef.value = Array.from(merged.values())
}

/* ---------- lifecycle ---------- */
onMounted(async () => {
  await ensureSession()
  sessionReady.value = true

  try {
    const res = await safeFrappeCall({ method: 'crm.api.lead_filters.drawer_options' })
    const d = res.message || {}
    fullProjectCatalog.value = (d.projects || []).map((v) => ({ label: v, value: v }))
    fullLocationCatalog.value = (d.locations || []).map((v) => ({ label: v, value: v }))
    fullSourceCatalog.value  = (d.source || []).map((v) => ({ label: v, value: v }))
    fullOriginCatalog.value  = (d.lead_origin || []).map((v) => ({ label: v, value: v }))
    fullTypeCatalog.value    = (d.lead_type || []).map((v) => ({ label: v, value: v }))
  } catch (e) {
    console.warn('drawer_options failed', e)
  }

  await loadProjectsCatalog()

  // ✅ let ViewControls own its lifecycle; just one initial reload
  viewControls.value?.reload?.()
  scheduleDelayedMapRefresh()

  try { window.__LEADS_VIEWCONTROLS__ = viewControls } catch (e) { /* noop */ }
})

if (typeof window !== 'undefined') {
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) {
      viewControls.value?.reload?.()
      scheduleDelayedMapRefresh()
    }
  })
}

/* ---------- stores / helpers ---------- */
const { makeCall } = globalStore()
const { getUser } = usersStore()
const statusStoreInstance = statusesStore()

const ownerList = computed(() => {
  return []
})

function getLeadStatusSafe(statusName) {
  if (!statusName) return { color: 'bg-gray-400' }
  const storeGetter = statusStoreInstance?.getLeadStatus?.(statusName)
  if (storeGetter && storeGetter.color) return storeGetter

  const local = statusList.value.find((x) => x.value === statusName || x.label === statusName)
  if (local) return { ...local, color: local.color || 'bg-gray-400' }

  return { color: 'bg-gray-400' }
}



/* ---------- rows / table shaping ---------- */
function getRow(name, field) {
  function wrap(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : { label: value }
  }
  return wrap(rows.value?.find((row) => row.name == name)?.[field])
}

const rows = computed(() => {
  if (!leads.value?.data?.data) return []
  if (leads.value.data.view_type === 'group_by') {
    if (!leads.value?.data.group_by_field?.fieldname) return []
    return getGroupedByRows(
      leads.value?.data.data,
      leads.value?.data.group_by_field,
      leads.value.data.columns
    )
  } else if (leads.value.data.view_type === 'kanban') {
    return getKanbanRows(leads.value.data.data, leads.value.data.fields)
  } else {
    return parseRows(leads.value?.data.data, leads.value.data.columns)
  }
})

/* ---- Debounced seen-values cache update ---- */
const updateSeenDebounced = useDebounceFn((newRows = []) => {
  const projMap = new Map(seenProjects.value.map((p) => [p.value, p]))
  const statusMap = new Map(seenStatuses.value.map((s) => [s.value || s.label, s]))
  const locMap = new Map(seenLocations.value.map((o) => [o.value, o]))
  const srcMap = new Map(seenSources.value.map((o) => [o.value, o]))
  const orgMap = new Map(seenOrigins.value.map((o) => [o.value, o]))
  const typMap = new Map(seenTypes.value.map((o) => [o.value, o]))
  const stgMap = new Map(seenStages.value.map((o) => [o.value, o]))

  newRows.forEach((r) => {
    const projField = r.project?.value || r.project?.label || r.project
    if (projField && !projMap.has(projField)) {
      projMap.set(projField, { label: projField, value: projField })
    }

    const rawStatus = r.status?.value || r.status?.label || r.status || ''
    if (rawStatus && !statusMap.has(rawStatus)) {
      statusMap.set(rawStatus, {
        label: rawStatus,
        value: rawStatus,
        color: r.status?.color || 'bg-gray-400'
      })
    }

    const pushSeen = (v, m) => { if (v && !m.has(v)) m.set(v, { label: v, value: v }) }
    pushSeen(r.location?.value || r.location?.label || r.location, locMap)
    pushSeen(r.lead_source?.value || r.lead_source?.label || r.lead_source, srcMap)
    pushSeen(r.lead_origin?.value || r.lead_origin?.label || r.lead_origin, orgMap)
    pushSeen(r.lead_type?.value || r.lead_type?.label || r.lead_type, typMap)
    pushSeen(r.stage?.value || r.stage?.label || r.stage, stgMap)
  })

  seenProjects.value  = Array.from(projMap.values())
  seenStatuses.value  = Array.from(statusMap.values())
  seenLocations.value = Array.from(locMap.values())
  seenSources.value   = Array.from(srcMap.values())
  seenOrigins.value   = Array.from(orgMap.values())
  seenTypes.value     = Array.from(typMap.values())
  seenStages.value    = Array.from(stgMap.values())
}, 150)

watch(rows, (newRows) => updateSeenDebounced(newRows), { immediate: true })

/* ---------- dropdown lists given to children ---------- */
const projectList = computed(() => {
  const merged = new Map()
  ;(fullProjectCatalog.value || []).forEach((p) => {
    if (p.value && !merged.has(p.value)) merged.set(p.value, p)
  })
  ;(seenProjects.value || []).forEach((p) => {
    if (p.value && !merged.has(p.value)) merged.set(p.value, p)
  })
  return Array.from(merged.values())
})

const statusList = computed(() => {
  const outMap = new Map()
  const storeArrays = []
  if (Array.isArray(statusStoreInstance.statuses)) storeArrays.push(statusStoreInstance.statuses)
  if (statusStoreInstance.statuses?.lead) storeArrays.push(statusStoreInstance.statuses.lead)
  if (Array.isArray(statusStoreInstance.statuses?.['CRM Lead'])) {
    storeArrays.push(statusStoreInstance.statuses['CRM Lead'])
  }
  const globalStatusArray = storeArrays.flat()

  globalStatusArray.forEach((s) => {
    const val = s?.value || s?.name || s?.label || (typeof s === 'string' ? s : '')
    if (!val) return
    const lbl = s.label || s.name || s.value || val
    const info = statusStoreInstance.getLeadStatus?.(val) || {}
    outMap.set(val, {
      label: lbl,
      value: val,
      color: info.color || s.color || 'bg-gray-400'
    })
  })

  ;(seenStatuses.value || []).forEach((s) => {
    const val = s.value || s.label || s.name || (typeof s === 'string' ? s : '')
    if (!val || outMap.has(val)) return
    const lbl = s.label || s.name || s.value || val
    const info = statusStoreInstance.getLeadStatus?.(val) || {}
    outMap.set(val, {
      label: lbl,
      value: val,
      color: info.color || 'bg-gray-400'
    })
  })

  return Array.from(outMap.values())
})

const locationList = computed(() => {
  const m = new Map(fullLocationCatalog.value.map((o) => [o.value, o]))
  ;(seenLocations.value || []).forEach((o) => {
    if (!m.has(o.value)) m.set(o.value, o)
  })
  return Array.from(m.values())
})

const sourceList = computed(() => {
  const m = new Map(fullSourceCatalog.value.map((o) => [o.value, o]))
  ;(seenSources.value || []).forEach((o) => {
    if (!m.has(o.value)) m.set(o.value, o)
  })
  return Array.from(m.values())
})

const originList = computed(() => {
  const m = new Map(fullOriginCatalog.value.map((o) => [o.value, o]))
  ;(seenOrigins.value || []).forEach((o) => {
    if (!m.has(o.value)) m.set(o.value, o)
  })
  return Array.from(m.values())
})

const typeList = computed(() => {
  const m = new Map(fullTypeCatalog.value.map((o) => [o.value, o]))
  ;(seenTypes.value || []).forEach((o) => {
    if (!m.has(o.value)) m.set(o.value, o)
  })
  return Array.from(m.values())
})

/* ---------- filter helpers ---------- */
function toTuples(filters = []) {
  const DOC = 'CRM Lead'
  return (filters || [])
    .filter((f) => f && (Array.isArray(f) || (f.fieldname && f.operator !== undefined)))
    .map((f) => (Array.isArray(f) ? f : [DOC, f.fieldname, f.operator, f.value]))
}

const LAST_CONTACT_FIELD = computed(() => {
  const fields = getLeadFields() || []
  const candidates = ['last_contacted_on', 'last_contacted', 'last_contact_date', 'last_contact']
  return (
    fields.find((f) => candidates.includes(f.fieldname)) || {
      fieldname: 'last_contacted_on',
      fieldtype: 'Datetime'
    }
  )
})

let _raf = 0
function scheduleApply(fn) {
  if (_raf) cancelAnimationFrame(_raf)
  _raf = requestAnimationFrame(() => {
    _raf = 0
    fn()
  })
}

const PROJECT_FIELD = computed(() => {
  if (getLeadFieldMeta('real_estate_project')) return 'real_estate_project'
  if (getLeadFieldMeta('project')) return 'project'
  return 'real_estate_project'
})

const LOCATION_FIELD = computed(() => {
  const candidates = ['territory', 'location', 'crm_location', 'lead_territory']
  for (const f of candidates) {
    if (getLeadFieldMeta(f)) return f
  }
  return 'territory'
})

const SPACE_FIELD = computed(() => {
  const candidates = ['space', 'area', 'unit_area', 'property_space', 'required_space']
  for (const f of candidates) if (getLeadFieldMeta(f)) return f
  return 'space'
})

const BUDGET_FIELD = computed(() => {
  const candidates = ['budget', 'expected_budget', 'max_budget', 'price', 'estimated_budget']
  for (const f of candidates) if (getLeadFieldMeta(f)) return f
  return 'budget'
})

function sanitizeFilters(arr = []) {
  const out = []
  for (const f of arr) {
    if (!f) continue

    const fieldname = Array.isArray(f) ? f[1] : f.fieldname || ''
    const operator  = Array.isArray(f) ? f[2] : f.operator  || ''
    const value     = Array.isArray(f) ? f[3]
      : (Object.prototype.hasOwnProperty.call(f, 'value') ? f.value : undefined)

    if (!fieldname || !operator) continue
    if (value === null || value === undefined || value === '') continue

    if (String(operator).toLowerCase() === 'between') {
      if (!Array.isArray(value) || value.length !== 2 ||
          value[0] == null || value[1] == null) continue
    }

    out.push({ fieldname, operator, value })
  }
  return out
}

/* ----------- FIXED: never dedupe away >= / <= ----------- */
function applyFilters(filters = [], replace = false) {
  const vc = viewControls.value
  if (!vc) {
    return
  }

  const DOC = 'CRM Lead'
  const tuples = []

  for (const f of (filters || [])) {
    if (!f?.fieldname || f.value === '' || f.value === null || f.value === undefined) continue
    // Convert value to proper type for Check fields (delayed is a Check field)
    let value = f.value
    if (f.fieldname === 'delayed') {
      // Ensure delayed is 1 or 0 (not boolean)
      value = value ? 1 : 0
    }
    tuples.push([DOC, f.fieldname, String(f.operator || '=').toLowerCase(), value])
  }

  // pagination reset
  loadMore.value = 1
  updatedPageCount.value = 20

  if (tuples.length === 0) {
    // Clear filters if no filters provided
    try {
      if (typeof vc.clearFilters === 'function') {
        vc.clearFilters()
        vc.reload?.()
      }
    } catch (e) {
      console.warn('[Leads] clearFilters failed (non-fatal):', e)
    }
    return
  }

  try {
    if (typeof vc.setFilters === 'function') {
      // setFilters always replaces filters, which is what we want for query params
      vc.setFilters(tuples)
    } else if (typeof vc.applyFilter === 'function') {
      // Apply all filters at once with replace flag
      vc.applyFilter({ filters: tuples, replace: replace })
    }
  } catch (e) {
    console.error('[Leads] apply/set filters error:', e)
  }

  // Don't call reload here - setFilters/applyFilter already trigger reload
}

// apply route query -> filters for the Leads page

// helper: map route.query to your internal filter payload
// helper: map route.query to your internal filter payload AND update the QuickFiltersBar model (ui)
function applyQueryFilters(query = {}) {
  // Update the QuickFiltersBar model so the UI reflects the selected filter
  ui.status = query.status || ''
  ui.lead_type = query.type || ''
  ui.priority = query.priority || ''
  // if you have follow_up logic that maps to the UI, set it here:
  ui.follow_up = query.follow_up || ''
  
  // Update project filter in UI
  if (query.project) {
    ui.project = query.project
  }
  
  // Update user/owner filter in UI
  if (query.user) {
    ui.owner = query.user
  }

  // build an F array like applyFiltersFromPanel or applyFilters expects
  const F = []

  if (query.status)    F.push({ fieldname: 'status', operator: '=', value: query.status })
  if (query.type)      F.push({ fieldname: 'lead_type', operator: '=', value: query.type })
  if (query.priority)  F.push({ fieldname: 'priority', operator: '=', value: query.priority })
  
  // Support delayed filter
  if (query.delayed !== undefined && query.delayed !== null && query.delayed !== '') {
    const delayedValue = query.delayed === '1' || query.delayed === 1 || query.delayed === true || query.delayed === 'true'
    F.push({ fieldname: 'delayed', operator: '=', value: delayedValue ? 1 : 0 })
  }
  
  // Support project filter
  if (query.project) {
    F.push({ fieldname: PROJECT_FIELD.value, operator: '=', value: query.project })
  }
  
  // Support user/owner filter
  if (query.user) {
    F.push({ fieldname: 'lead_owner', operator: '=', value: query.user })
  }

  if (query.follow_up) {
    // example: 'today' mapping — adapt to your app's follow_up field if needed
    if (query.follow_up === 'today') {
      // if you map follow_up to a field on UI, update ui accordingly above and add filter here
      // e.g. F.push({ fieldname: 'follow_up_date', operator: '=', value: today })
    }
  }

  if (query.create) {
    // keep existing behavior: open create modal if `create=1`
    showLeadModal.value = true
  }

  // apply filters (this will also reload the viewControls)
  // Use replace: true to replace all existing filters with query filters
  if (F.length) {
    applyFilters(F, true)  // replace: true to clear old filters and apply new ones
  } else {
    // clear existing filters so QuickFiltersBar + list stay in sync
    applyFilters([], true)  // Empty array with replace will clear all filters
  }
}

// Store pending query filters to apply when viewControls is ready
const pendingQueryFilters = ref(null)

// Watch for viewControls to be ready, then apply pending filters
watch(
  () => viewControls.value,
  (vc) => {
    if (vc && pendingQueryFilters.value) {
      const query = pendingQueryFilters.value
      pendingQueryFilters.value = null
      // Use nextTick to ensure viewControls is fully initialized
      setTimeout(() => {
        applyQueryFilters(query)
      }, 50)
    }
  }
)

// run on initial load and whenever query changes
watch(
  () => route.query,
  (q) => {
    const query = q || {}
    // If viewControls is ready, apply filters immediately
    if (viewControls.value) {
      applyQueryFilters(query)
    } else {
      // Store query to apply when viewControls is ready
      pendingQueryFilters.value = query
    }
  },
  { immediate: true }
)

function applyLike(list) {
  scheduleApply(() => {
    const vc = viewControls.value
    if (!vc) return

    loadMore.value = 1
    updatedPageCount.value = 20

    try { vc.clearLikeFilters?.() } catch {}

    if (!Array.isArray(list) || !list.length) {
      vc.reload?.()
      return
    }

    for (const f of list) {
      if (!f?.fieldname || f.value == null || f.value === '') continue
      const payload = { fieldname: f.fieldname, operator: 'like', value: `%${f.value}%` }
      if (vc.applyLikeFilter) vc.applyLikeFilter(payload)
      else if (vc.applyFilter) vc.applyFilter({ filters: toTuples([payload]), replace: false })
    }

    vc.reload?.()
  })
}

/* ---------- Drawer (All Filters) ---------- */
const showFilters = ref(false)
const ui = reactive({
  status: '',
  stage: '',
  project: '',
  last_contacted_from: '',
  last_contacted_to: '',
  location: '',
  space_min: '',
  space_max: '',
  budget_min: '',
  budget_max: '',
  lead_source: '',
  lead_origin: '',
  lead_type: ''
})

function toNum(v) {
  if (v === '' || v == null) return null
  let s = String(v).trim().lowerCase?.() ?? String(v).trim().toLowerCase()

  const map = { '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9' }
  s = s.replace(/[٠-٩]/g, d => map[d])

  s = s.replace(/\s+/g, '').replace(/[,،]/g, '')

  let mult = 1
  if (s.endsWith('k')) { mult = 1e3; s = s.slice(0, -1) }
  else if (s.endsWith('m')) { mult = 1e6; s = s.slice(0, -1) }
  else if (s.endsWith('b')) { mult = 1e9; s = s.slice(0, -1) }

  s = s.replace(/[^\d.]/g, '')

  if (!s) return null
  const n = Number(s)
  return Number.isFinite(n) ? n * mult : null
}

function applyFiltersFromPanel(draft = {}) {
  Object.assign(ui, {
    status:              firstKey(draft, ['status'], ''),
    project:             firstKey(draft, ['project'], ''),
    location:            firstKey(draft, ['territory','location','crm_location','lead_territory'], ''),
    last_contacted_from: firstKey(draft, ['last_contacted_from','lastFrom','from_date'], ''),
    last_contacted_to:   firstKey(draft, ['last_contacted_to','lastTo','to_date'], ''),
    space_min:           firstKey(draft, ['space_min','spaceFrom','min_space','minSpace','area_min','min_area'], ui.space_min),
    space_max:           firstKey(draft, ['space_max','spaceTo','max_space','maxSpace','area_max','max_area'], ui.space_max),
    budget_min:          firstKey(draft, ['budget_min','budgetFrom','min_budget','minBudget','price_min','min_price','expected_budget_min'], ui.budget_min),
    budget_max:          firstKey(draft, ['budget_max','budgetTo','max_budget','maxBudget','price_max','max_price','expected_budget_max'], ui.budget_max),
    lead_source:         firstKey(draft, ['lead_source','source'], ''),
    lead_origin:         firstKey(draft, ['lead_origin','origin'], ''),
    lead_type:           firstKey(draft, ['lead_type','type'], ''),
  })

  const bMin = toNum(ui.budget_min)
  const bMax = toNum(ui.budget_max)
  const sMin = toNum(ui.space_min)
  const sMax = toNum(ui.space_max)

  const F = []

  if (ui.status)      F.push({ fieldname: 'status', operator: '=', value: ui.status })
  if (ui.project)     F.push({ fieldname: PROJECT_FIELD.value, operator: '=', value: ui.project })
  if (ui.location)    F.push({ fieldname: LOCATION_FIELD.value, operator: '=', value: ui.location })
  if (ui.lead_source) F.push({ fieldname: SOURCE_FIELD.value, operator: '=', value: ui.lead_source })
  if (ui.lead_origin) F.push({ fieldname: 'lead_origin', operator: '=', value: ui.lead_origin })
  if (ui.lead_type)   F.push({ fieldname: 'lead_type',   operator: '=', value: ui.lead_type })

  // Dates → >= / <= only
  if (ui.last_contacted_from) {
    F.push({ fieldname: LAST_CONTACT_FIELD.value.fieldname, operator: '>=', value: ui.last_contacted_from })
  }
  if (ui.last_contacted_to) {
    const isDT = (LAST_CONTACT_FIELD.value.fieldtype || '').toLowerCase() === 'datetime'
    const end = isDT ? `${ui.last_contacted_to} 23:59:59` : ui.last_contacted_to
    F.push({ fieldname: LAST_CONTACT_FIELD.value.fieldname, operator: '<=', value: end })
  }

  // Budget
  if (bMin !== null) F.push({ fieldname: BUDGET_FIELD.value, operator: '>=', value: bMin })
  if (bMax !== null) F.push({ fieldname: BUDGET_FIELD.value, operator: '<=', value: bMax })

  // Space
  if (sMin !== null) F.push({ fieldname: SPACE_FIELD.value, operator: '>=', value: sMin })
  if (sMax !== null) F.push({ fieldname: SPACE_FIELD.value, operator: '<=', value: sMax })

  applyFilters(F)
  showFilters.value = false
}

function clearDrawer() {
  Object.assign(ui, {
    owner_mode: 'all',
    status: '',
    converted: 'no',
    project: '',
    last_contacted_from: '',
    last_contacted_to: '',
    location: '',
    space_min: null,
    space_max: null,
    budget_min: null,
    budget_max: null,
    lead_source: '',
    lead_origin: '',
    lead_type: '',
    has_phone: false,
    has_email: false,
    stage: ''
  })
}

/* ---------- Inject Last Comment + Delayed columns if missing ---------- */
const columnsForList = ref(null)

watch(
  () => leads.value?.data?.columns,
  (cols) => {
    if (!cols) return

    const ensured = [...cols]

    if (!ensured.some(c => (c.key || c.value) === 'latest_comment')) {
      ensured.push({
        key: 'latest_comment',
        label: __('Latest Comment'),
        type: 'Data',
        width: 600,
      })
    }

    columnsForList.value = ensured
  },
  { immediate: true }
)

/* ---------- Delayed flag map ---------- */
function getVisibleLeadNames() {
  const payload = leads.value?.data
  if (!payload?.data) return []

  const rows = Array.isArray(payload.data)
    ? payload.data
    : Array.isArray(payload.data?.data)
      ? payload.data.data
      : []
  if (!rows.length) return []

  const pluckNames = (arr = []) =>
    arr
      .map((row) => row?.name)
      .filter((name) => typeof name === 'string' && name.length)

  if (payload.view_type === 'group_by') {
    return rows.flatMap((group) => pluckNames(group?.data || []))
  }
  if (payload.view_type === 'kanban') {
    return rows.flatMap((column) => pluckNames(column?.data || []))
  }
  return pluckNames(Array.isArray(rows) ? rows : [])
}

const scheduleDelayedMapRefresh = useDebounceFn(async () => {
  const names = getVisibleLeadNames()
  if (!names.length) {
    lastDelayedNamesKey = ''
    delayedMap.value = {}
    return
  }

  const unique = Array.from(new Set(names))
  const newKey = unique.join('|')
  const namesChanged = newKey !== lastDelayedNamesKey
  if (namesChanged) {
    delayedMap.value = {}
  }

  const freshMap = {}

  try {
    for (let i = 0; i < unique.length; i += MAX_DELAYED_BATCH) {
      const chunk = unique.slice(i, i + MAX_DELAYED_BATCH)
      const res = await safeFrappeCall({
        method: 'crm.api.reminders.get_delayed_map',
        args: { lead_names: chunk },
      })
      Object.assign(freshMap, res?.message || {})
    }
    delayedMap.value = freshMap
    lastDelayedNamesKey = newKey
  } catch (err) {
    console.warn('[Leads] delayed map fetch failed', err)
    delayedMap.value = {}
  }
}, 250)

watch(
  () => leads.value?.data?.data,
  () => scheduleDelayedMapRefresh()
)

watch(
  () => leads.value?.data?.view_type,
  () => scheduleDelayedMapRefresh()
)

watch(
  () => route.params.viewType,
  () => scheduleDelayedMapRefresh()
)

watch(
  () => leads.value?.loading,
  (loading, prev) => {
    if (prev && loading === false) scheduleDelayedMapRefresh()
  }
)

onActivated(() => scheduleDelayedMapRefresh())

/* ---------- data shaping helpers ---------- */
function getGroupedByRows(listRows, groupByField, columns) {
  let groupedRows = []
  groupByField.options?.forEach((option) => {
    let filteredRows = !option
      ? listRows.filter((row) => !row[groupByField.fieldname])
      : listRows.filter((row) => row[groupByField.fieldname] == option)

    let groupDetail = {
      label: groupByField.label,
      group: option || __(' '),
      collapsed: false,
      rows: parseRows(filteredRows, columns)
    }

    if (groupByField.fieldname == 'status') {
      groupDetail.icon = () => h(IndicatorIcon, { class: getLeadStatusSafe(option)?.color })
    }
    groupedRows.push(groupDetail)
  })
  return groupedRows || listRows
}

function getKanbanRows(data, columns) {
  let _rows = []
  data.forEach((column) => column.data?.forEach((row) => _rows.push(row)))
  return parseRows(_rows, columns)
}

function parseRows(rowsIn, columns = []) {
  const delayedLookup = delayedMap.value || {}
  let view_type = leads.value.data.view_type
  let key = view_type === 'kanban' ? 'fieldname' : 'key'
  let type = view_type === 'kanban' ? 'fieldtype' : 'type'

  return rowsIn.map((lead) => {
    let _rows = {}
    const leadName = lead?.name

    leads.value?.data.rows.forEach((row) => {
      _rows[row] = lead[row]
      let fieldType = columns?.find((col) => (col[key] || col.value) == row)?.[type]

      if (fieldType && ['Date', 'Datetime'].includes(fieldType) && !['modified', 'creation'].includes(row)) {
        _rows[row] = formatDate(lead[row], '', true, fieldType == 'Datetime')
      }
      if (fieldType && fieldType == 'Currency') _rows[row] = getFormattedCurrency(row, lead)
      if (fieldType && fieldType == 'Float')    _rows[row] = getFormattedFloat(row, lead)
      if (fieldType && fieldType == 'Percent')  _rows[row] = getFormattedPercent(row, lead)

      if (row === 'lead_name') {
        _rows[row] = {
          label: lead.lead_name,
          image: lead.image,
          image_label: lead.first_name
        }
      } else if (row === 'organization') {
        _rows[row] = lead.organization
      } else if (row === 'website') {
        _rows[row] = website(lead.website)
      } else if (row === 'status') {
        _rows[row] = {
          label: lead.status,
          color: getLeadStatusSafe(lead.status).color,
          value: lead.status
        }
      } else if (row === 'project') {
        const projVal = lead.project
        _rows[row] = { label: projVal || '', value: projVal || '' }
      } else if (row === 'sla_status') {
        let value = lead.sla_status
        let tooltipText = value
        let color = value == 'Failed' ? 'red' : value == 'Fulfilled' ? 'green' : 'orange'

        if (value == 'First Response Due') {
          value = __(timeAgo(lead.response_by))
          tooltipText = formatDate(lead.response_by)
          if (new Date(lead.response_by) < new Date()) color = 'red'
        }
        _rows[row] = { label: tooltipText, value, color }
      } else if (row === 'lead_owner') {
        _rows[row] = {
          label: lead.lead_owner && getUser(lead.lead_owner).full_name,
          ...(lead.lead_owner && getUser(lead.lead_owner))
        }
      } else if (row === '_assign') {
        let assignees = JSON.parse(lead._assign || '[]')
        _rows[row] = assignees.map((user) => ({
          name: user,
          image: getUser(user).user_image,
          label: getUser(user).full_name
        }))
      } else if (['modified', 'creation'].includes(row)) {
        _rows[row] = {
          label: formatDate(lead[row]),
          timeAgo: __(timeAgo(lead[row]))
        }
      } else if (['first_response_time', 'first_responded_on', 'response_by'].includes(row)) {
        let field = row === 'response_by' ? 'response_by' : 'first_responded_on'
        _rows[row] = {
          label: lead[field] ? formatDate(lead[field]) : '',
          timeAgo: lead[row]
            ? row === 'first_response_time'
              ? formatTime(lead[row])
              : __(timeAgo(lead[row]))
            : ''
        }
      }
    })

    // counts
    _rows['_email_count'] = lead._email_count
    _rows['_note_count']  = lead._note_count
    _rows['_task_count']  = lead._task_count
    _rows['_comment_count'] = lead._comment_count

    // Last FeedBack if available
    const lastC =
      lead.last_comment || lead.last_feedback || lead._last_comment || lead._last_feedback || ''
    _rows['last_comment'] = lastC;
    const docDelayed = Boolean(lead?.delayed)
    const hasMapValue = leadName
      ? Object.prototype.hasOwnProperty.call(delayedLookup, leadName)
      : false
    const mapValue = hasMapValue ? Boolean(delayedLookup[leadName]) : undefined
    _rows['delayed'] = hasMapValue ? mapValue : docDelayed

    return _rows
  })
}

/* ---------- actions / modals ---------- */
function onNewClick(column) {
  let column_field = leads.value.params?.column_field
  if (column_field) defaults[column_field] = column.column.name
  showLeadModal.value = true
}

function actions(itemName) {
  let mobile_no = getRow(itemName, 'mobile_no')?.label || ''
  let actions = [
    {
      icon: h(PhoneIcon, { class: 'h-4 w-4' }),
      label: __('Make a Call'),
      onClick: () => makeCall(mobile_no),
      condition: () => mobile_no && callEnabled.value
    },
    {
      icon: h(NoteIcon, { class: 'h-4 w-4' }),
      label: __('New Note'),
      onClick: () => showNote(itemName)
    },
    {
      icon: h(TaskIcon, { class: 'h-4 w-4' }),
      label: __('New Task'),
      onClick: () => showTask(itemName)
    }
  ]
  return actions.filter((a) => (a.condition ? a.condition() : true))
}

const docname = ref('')
const showNoteModal = ref(false)
const note = ref({ title: '', content: '' })
function showNote(name) {
  docname.value = name
  showNoteModal.value = true
}

const showTaskModal = ref(false)
const task = ref({
  title: '',
  task_type: '',
  description: '',
  assigned_to: '',
  due_date: '',
  priority: 'Low',
  status: 'Backlog'
})
function showTask(name) {
  docname.value = name
  showTaskModal.value = true
}
</script>
