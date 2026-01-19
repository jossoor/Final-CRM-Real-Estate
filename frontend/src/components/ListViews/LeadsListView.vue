<template>
  <ListView
    :class="$attrs.class"
    :columns="columns"
    :rows="rows"
    :options="{
      selectable: options.selectable,
      showTooltip: options.showTooltip,
      resizeColumn: options.resizeColumn,
    }"
    row-key="name"
    ref="listViewRef"
    v-model:selections="selections"
    :key="listViewKey"
  >
    <ListHeader class="sm:mx-5 mx-3" @columnWidthUpdated="emit('columnWidthUpdated')">
      <ListHeaderItem
        v-for="column in columns"
        :key="column.key"
        :item="column"
        :align="column.key === 'status' ? 'center' : column.align"
        :class="column.key === 'status' ? 'status-header' : ''"
        @columnWidthUpdated="emit('columnWidthUpdated', column)"
      >
        <Button
          v-if="column.key == '_liked_by'"
          variant="ghosted"
          class="!h-4"
          :class="isLikeFilterApplied ? 'fill-red-500' : 'fill-white'"
          @click="() => emit('applyLikeFilter')"
        >
          <HeartIcon class="h-4 w-4" />
        </Button>
      </ListHeaderItem>
    </ListHeader>

    <ListRows :rows="rows" v-slot="{ idx, column, item, row }" doctype="CRM Lead">
      <!-- المكلّفين -->
      <div
        v-if="column.key === '_assign'"
        class="h-full w-full"
        :class="row.original_lead ? 'highlight-yellow' : ''"
      >
        <MultipleAvatar
          :avatars="item"
          size="sm"
          @click="
            (event) =>
              emit('applyFilter', { event, idx, column, item, firstColumn: columns[0] })
          "
        />
      </div>

      <!-- عمود آخر كومنت (Quick form) -->
      <div
        v-else-if="column.key === 'last_comment'"
        class="h-full w-full"
        :class="row.original_lead ? 'highlight-yellow' : ''"
        @click.stop
        @mousedown.stop
        @mouseup.stop
        @dblclick.stop
      >
        <LeadCommentsQuick :leadName="row.name" />
      </div>

      <!-- باقي الأعمدة -->
      <div
        v-else
        class="h-full w-full"
        :class="row.original_lead ? 'highlight-yellow' : ''"
      >
        <ListRowItem 
          :item="item" 
          :align="column.key === 'status' ? 'center' : column.align"
          :class="column.key === 'status' ? 'status-cell' : ''"
        >
          <template #prefix>
            <div v-if="column.key === 'status'">
              <!-- Don't show indicator icon for status dropdown -->
            </div>
            <div v-else-if="column.key === 'lead_name'">
              <Avatar
                v-if="item.label"
                class="flex items-center"
                :image="item.image"
                :label="item.image_label"
                size="sm"
              />
            </div>
            <div v-else-if="column.key === 'lead_owner'">
              <Avatar
                v-if="item.full_name"
                class="flex items-center"
                :image="item.user_image"
                :label="item.full_name"
                size="sm"
              />
            </div>
          </template>

          <template #default="{ label }">
            <!-- اجعل فتح صفحة الـ Lead على الاسم فقط -->
            <div v-if="column.key === 'lead_name'">
              <RouterLink
                class="text-ink-blue-7 hover:underline"
                :to="{
                  name: 'Lead',
                  params: { leadId: row.name },
                  query: { view: route.query.view, viewType: route.params.viewType },
                }"
                @click.stop
              >
                {{ item?.label || label }}
              </RouterLink>
            </div>

            <!-- الموبايل + اتصال + SMS + واتساب -->
            <div
              v-else-if="column.key === 'mobile_no'"
              class="flex items-center justify-between gap-2"
            >
              <div class="flex items-center gap-2 min-w-0">
                <span>
                  {{ typeof item === 'object' && item ? item.label : item }}
                </span>
              </div>

              <div class="flex items-center gap-1 shrink-0">
                <!-- Call -->
                <Button
                  v-if="getMobile(row)"
                  variant="ghost"
                  class="!p-1"
                  @click.stop="makeCall(getMobile(row))"
                  :title="__('Call')"
                  aria-label="Call"
                >
                  <PhoneIcon class="h-4 w-4" />
                </Button>

                <!-- ✅ SMS (between Call + WhatsApp) -->
                <Button
                  v-if="getMobile(row)"
                  variant="ghost"
                  class="!p-1"
                  @click.stop="sendSMS(getMobile(row))"
                  :title="__('Send SMS')"
                  aria-label="Send SMS"
                >
                  <FeatherIcon name="message-circle" class="h-4 w-4" />
                </Button>

                <!-- WhatsApp -->
                <Button
                  v-if="getMobile(row)"
                  variant="ghost"
                  class="!p-1"
                  @click.stop="openWhatsApp(getMobile(row))"
                  :title="__('Open WhatsApp')"
                  aria-label="Open WhatsApp"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" class="h-4 w-4" aria-hidden="true">
                    <path
                      fill="currentColor"
                      d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z"
                    />
                  </svg>
                </Button>
              </div>
            </div>

            <!-- STATUS DROPDOWN -->
            <div v-else-if="column.key === 'status'" class="flex justify-center items-center w-full">
              <select
                :value="item.value || item.label"
                @change="(e) => updateStatus(row.name, e.target.value, item, row)"
                @click.stop.prevent
                :class="['status-dropdown', getStatusClass(item.value || item.label)]"
              >
                <option
                  v-for="status in availableStatuses"
                  :key="status.value"
                  :value="status.value"
                >
                  {{ status.label }}
                </option>
              </select>
            </div>

            <!-- تواريخ -->
            <div
              v-else-if="
                ['modified','creation','first_response_time','first_responded_on','response_by'].includes(column.key)
              "
              class="truncate text-base"
              @click="
                (event) =>
                  emit('applyFilter', {
                    event,
                    idx,
                    column,
                    item,
                    firstColumn: columns[0],
                  })
              "
            >
              <Tooltip :text="item.label">
                <div>{{ item.timeAgo }}</div>
              </Tooltip>
            </div>

            <!-- لايك -->
            <div v-else-if="column.key === '_liked_by'">
              <Button
                variant="ghosted"
                :class="isLiked(item) ? 'fill-red-500' : 'fill-white'"
                @click.stop.prevent="
                  () => emit('likeDoc', { name: row.name, liked: isLiked(item) })
                "
              >
                <HeartIcon class="h-4 w-4" />
              </Button>
            </div>

            <!-- SLA -->
            <div v-else-if="column.key === 'sla_status'" class="truncate text-base">
              <Badge
                v-if="item.value"
                :variant="'subtle'"
                :theme="item.color"
                size="md"
                :label="item.value"
                @click="
                  (event) =>
                    emit('applyFilter', {
                      event,
                      idx,
                      column,
                      item,
                      firstColumn: columns[0],
                    })
              "
              />
            </div>

            <!-- Check -->
            <div v-else-if="column.type === 'Check'">
              <FormControl
                type="checkbox"
                :modelValue="item"
                :disabled="true"
                class="text-ink-gray-9"
              />
            </div>

            <!-- باقي الأعمدة -->
            <div
              v-else
              class="truncate text-base"
              @click="
                (event) =>
                  emit('applyFilter', {
                    event,
                    idx,
                    column,
                    item,
                    firstColumn: columns[0],
                  })
              "
            >
              {{ label }}
            </div>
          </template>
        </ListRowItem>
      </div>
    </ListRows>
  </ListView>

  <!-- Custom Floating Selection Bar -->
  <transition name="slide-up">
    <div
      v-if="selections.size > 0"
      class="fixed bottom-10 left-1/2 z-[100] flex -translate-x-1/2 items-center gap-6 rounded-2xl bg-[#1e2128] px-6 py-3 shadow-2xl ring-1 ring-white/10"
    >
      <!-- Selection Count Badge -->
      <div class="flex items-center gap-3 border-r border-white/10 pr-6">
        <div
          class="flex h-6 w-6 items-center justify-center rounded bg-white/10 text-xs font-bold text-white"
        >
          {{ selections.size }}
        </div>
        <span class="text-sm font-medium text-white">{{ __('Leads Selected') }}</span>
      </div>

      <!-- Action Buttons -->
      <div class="flex items-center gap-1">
        <button
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/5 active:bg-white/10"
          @click="listBulkActionsRef.assignValues(selections, unselectAll)"
        >
          <FeatherIcon name="user-plus" class="h-4 w-4" />
          <span>{{ __('Assign Lead') }}</span>
        </button>

        <button
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/5 active:bg-white/10"
          @click="listBulkActionsRef.editValues(selections, unselectAll)"
        >
          <FeatherIcon name="edit-2" class="h-4 w-4 text-blue-400" />
          <span>{{ __('Edit') }}</span>
        </button>

        <button
          class="flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/5 active:bg-white/10"
          @click="listBulkActionsRef.deleteValues(selections, unselectAll)"
        >
          <FeatherIcon name="trash-2" class="h-4 w-4 text-red-400" />
          <span>{{ __('Delete') }}</span>
        </button>
      </div>

      <!-- Close/Unselect Button -->
      <button
        class="ml-2 flex h-8 w-8 items-center justify-center rounded-full text-white/50 transition-colors hover:bg-white/10 hover:text-white"
        @click="unselectAll"
      >
        <FeatherIcon name="x" class="h-4 w-4" />
      </button>
    </div>
  </transition>

  <CustomListFooter
    v-if="pageLengthCount"
    class="border-t sm:px-5 px-3 py-2"
    v-model="pageLengthCount"
    :options="{
      rowCount: options.rowCount,
      totalCount: options.totalCount,
    }"
    @loadMore="emit('loadMore')"
  />
  <ListBulkActions ref="listBulkActionsRef" v-model="list" doctype="CRM Lead" />
</template>

<script setup>
import LeadCommentsQuick from '@/components/LeadCommentsQuick.vue'
import HeartIcon from '@/components/Icons/HeartIcon.vue'
import IndicatorIcon from '@/components/Icons/IndicatorIcon.vue'
import PhoneIcon from '@/components/Icons/PhoneIcon.vue'
import MultipleAvatar from '@/components/MultipleAvatar.vue'
import ListBulkActions from '@/components/ListBulkActions.vue'
import ListRows from '@/components/ListViews/ListRows.vue'
import CustomListFooter from '@/components/CustomListFooter.vue'
import {
  Avatar,
  ListView,
  ListHeader,
  ListHeaderItem,
  ListSelectBanner,
  ListRowItem,
  Tooltip,
  Button,
  FormControl,
  Badge,
  Dropdown,
  FeatherIcon,
  call,
} from 'frappe-ui'
import { sessionStore } from '@/stores/session'
import { statusesStore } from '@/stores/statuses'
import { ref, computed, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'

const props = defineProps({
  rows: { type: Array, required: true },
  columns: { type: Array, required: true },
  options: {
    type: Object,
    default: () => ({
      selectable: true,
      showTooltip: true,
      resizeColumn: false,
      totalCount: 0,
      rowCount: 0,
    }),
  },
})
const emit = defineEmits([
  'loadMore',
  'updatePageCount',
  'columnWidthUpdated',
  'applyFilter',
  'applyLikeFilter',
  'likeDoc',
  'selectionsChanged',
])

const route = useRoute()
const pageLengthCount = defineModel()
const list = defineModel('list')

const listViewRef = ref(null)
const selections = ref(new Set())

const listViewKey = ref(0) // Used to force-reset ListView if needed

function updateSelections(val) {
  selections.value = val
  emit('selectionsChanged', val)
}

function unselectAll() {
  console.log('LeadsListView: unselectAll called')
  selections.value = new Set()
  emit('selectionsChanged', new Set())
  // Force a re-render of ListView to clear internal checkboxes
  listViewKey.value++
}

const isLikeFilterApplied = computed(() => {
  return list.value?.params?.filters?._liked_by ? true : false
})

const { user } = sessionStore()
const { statusOptions } = statusesStore()

// Available statuses - filtered to show only specific statuses
const allowedStatusList = [
  'New',
  'Contacted',
  'Nurture',
  'Qualified',
  'Unqualified',
  'Showing',
  'Other',
  'Follow Up',
  'Follow Up To Meeting',
  'No Answer',
  'Meeting',
  'Follow Up After Meeting',
  'Not Interested',
  'Rotation',
  'low budget',
  'Junk',
  'Reservation',
  'Done Deal'
]

const availableStatuses = computed(() => {
  const allStatuses = statusOptions('lead')
  return allStatuses.filter(status => allowedStatusList.includes(status.value))
})

// Check if status is in the allowed list
function isStatusInAllowedList(status) {
  return allowedStatusList.includes(status)
}

function isLiked(item) {
  if (!item) return false
  try {
    const likedByMe = JSON.parse(item)
    return likedByMe.includes(user)
  } catch {
    return false
  }
}

watch(pageLengthCount, (val, old_value) => {
  if (val === old_value) return
  emit('updatePageCount', val)
})

const listBulkActionsRef = ref(null)
defineExpose({
  customListActions: computed(
    () => listBulkActionsRef.value?.customListActions,
  ),
})

// Function to get status-specific CSS class
function getStatusClass(status) {
  const statusMap = {
    'New': 'status-new',
    'Contacted': 'status-contacted',
    'Nurture': 'status-nurture',
    'Qualified': 'status-qualified',
    'Unqualified': 'status-unqualified',
    'Showing': 'status-showing',
    'Other': 'status-other',
    'Follow Up': 'status-follow-up',
    'Follow Up To Meeting': 'status-follow-up-to-meeting',
    'No Answer': 'status-no-answer',
    'Meeting': 'status-meeting',
    'Follow Up After Meeting': 'status-follow-up-after-meeting',
    'Not Interested': 'status-not-interested',
    'Rotation': 'status-rotation',
    'low budget': 'status-low-budget',
    'Reservation': 'status-reservation',
    'Done Deal': 'status-done-deal',
    'Junk': 'status-junk'
  }
  
  return statusMap[status] || 'status-default'
}

// Function to update status
async function updateStatus(leadName, newStatus, currentItem, row) {
  console.log('🔄 Updating status...', { leadName, newStatus })

  try {
    // Perform the database update using our custom API to bypass potentially broken hooks
    await call('crm.api.doc.update_lead_status', {
      name: leadName,
      status: newStatus,
    })

    console.log('✅ Database updated successfully via custom API')

    // 1. Update the local row data IMMEDIATELY for instant UI feedback
    if (row) {
      row.status = newStatus
    }
    
    // 2. Update the cell item if it exists
    if (currentItem) {
      currentItem.value = newStatus
      currentItem.label = newStatus
    }

    // 3. Show success message
    if (window.$notify) {
      window.$notify({
        title: __('Status Updated'),
        message: __('Status changed to {0} for {1}', [newStatus, leadName]),
        type: 'success',
      })
    }

    // 4. Reload the list resource to ensure all derived fields/meta are correct
    if (list.value && typeof list.value.reload === 'function') {
      await list.value.reload()
    }
  } catch (error) {
    console.error('❌ Failed to update status:', error)

    // Show error message
    if (window.$notify) {
      window.$notify({
        title: 'Error',
        message: 'Failed to update status',
        type: 'error',
      })
    }
  }
}

/** Utils */
function getMobile(row) {
  const v = row?.mobile_no
  return typeof v === 'object' && v !== null ? v.label : v || ''
}
function makeCall(number) {
  const n = String(number || '').trim()
  if (n) window.open(`tel:${n}`)
}
function openWhatsApp(number) {
  const phone = String(number || '').replace(/\D/g, '')
  if (phone) window.open(`https://wa.me/${phone}`, '_blank')
}
function isMobileDevice() {
  if (typeof navigator === 'undefined') return false
  return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
}

function sendSMS(number) {
  if (!number) return

  const cleaned = String(number).replace(/\s+/g, '')
  const smsUrl = `sms:${encodeURIComponent(cleaned)}`

  // Just try to open the SMS app
  try {
    window.location.href = smsUrl
  } catch (e) {
    console.warn('Failed to open SMS handler', e)
  }
}

</script>

<style scoped>
.highlight-yellow {
  background-color: #FFFDF4 !important;
}

/* make sure header label and cells for status are centered even through wrapped components */
.status-header {
  display: flex;
  justify-content: center;
  align-items: center;
  text-align: center;
}

/* ensure any child content of header is centered (reach into component tree) */
::v-deep .status-header {
  display: flex;
  justify-content: center;
  align-items: center;
  text-align: center;
}

/* Center cell content and remove left padding that may cause visual offset */
.status-cell {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  padding-left: 0 !important;
  padding-right: 0 !important;
}

/* ensure the internal children of the row item are centered too */
::v-deep .status-cell {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  padding-left: 0 !important;
  padding-right: 0 !important;
}

/* The select itself — make it sit exactly centered */
.status-dropdown {
  display: inline-block;
  margin: 0 auto;
  appearance: none;
  padding: 5px 20px 5px 10px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 20px;
  border: none;
  cursor: pointer;
  transition: all 0.15s ease;
  min-width: 100px;
  background-repeat: no-repeat;
  background-position: right 6px center;
  background-size: 10px 10px;
  line-height: 1.3;
}

/* small tweak to ensure the native dropdown arrow doesn't push it off-center */
.status-dropdown::-ms-expand {
  display: none;
}

/* overrides for hover/focus/active */
.status-dropdown:hover {
  opacity: 0.95;
}

.status-dropdown:focus {
  outline: none;
  box-shadow: 0 0 0 3px rgba(0, 0, 0, 0.06);
}

.status-dropdown:active {
  transform: scale(0.995);
}

/* STATUS COLOR CLASSES */

/* New - Bright Blue */
.status-new {
  background-color: #bfdbfe;
  color: #1e40af;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%231e40af' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Follow Up - Light Purple */
.status-follow-up {
  background-color: #e9d5ff;
  color: #7c3aed;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%237c3aed' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Follow Up To Meeting - Deep Purple */
.status-follow-up-to-meeting {
  background-color: #c7d2fe;
  color: #4338ca;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%234338ca' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* No Answer - Light Gray/Blue */
.status-no-answer {
  background-color: #e0e7ff;
  color: #3730a3;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%233730a3' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Meeting - Cyan */
.status-meeting {
  background-color: #a5f3fc;
  color: #0e7490;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%230e7490' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Follow Up After Meeting - Teal */
.status-follow-up-after-meeting {
  background-color: #99f6e4;
  color: #0f766e;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%230f766e' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Not Interested - Red */
.status-not-interested {
  background-color: #fecaca;
  color: #991b1b;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23991b1b' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Rotation - Orange */
.status-rotation {
  background-color: #fed7aa;
  color: #c2410c;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23c2410c' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Contacted - Light Blue */
.status-contacted {
  background-color: #e0f2fe;
  color: #0369a1;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%230369a1' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Nurture - Amber */
.status-nurture {
  background-color: #fef3c7;
  color: #b45309;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23b45309' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Qualified - Emerald */
.status-qualified {
  background-color: #d1fae5;
  color: #047857;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23047857' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Unqualified - Slate */
.status-unqualified {
  background-color: #f1f5f9;
  color: #475569;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23475569' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Showing - Pink */
.status-showing {
  background-color: #fce7f3;
  color: #be185d;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23be185d' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Other - Neutral */
.status-other {
  background-color: #f3f4f6;
  color: #374151;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23374151' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

.status-junk {
  background-color: #fee2e2; /* soft red background */
  color: #b91c1c; /* strong red text */
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23b91c1c' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}


/* low budget - Yellow */
.status-low-budget {
  background-color: #fef3c7;
  color: #92400e;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%2392400e' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Reservation - Light Green */
.status-reservation {
  background-color: #d1fae5;
  color: #065f46;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23065f46' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Done Deal - Bright Green */
.status-done-deal {
  background-color: #86efac;
  color: #166534;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23166534' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Default fallback */
.status-default {
  background-color: #e5e7eb;
  color: #374151;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%23374151' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Legacy statuses (for old leads - gray style) */
.status-legacy {
  background-color: #f3f4f6;
  color: #6b7280;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%236b7280' d='M5 7L1 3h8z'/%3E%3C/svg%3E");
}

/* Style for dropdown options */
.status-dropdown option {
  padding: 8px 12px;
  background-color: white;
  color: #1f2937;
  font-weight: 500;
}

/* Disabled option styling (for legacy statuses) */
.status-dropdown option:disabled {
  color: #9ca3af;
  font-style: italic;
}

/* Custom Floating Bar Styles */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from,
.slide-up-leave-to {
  transform: translate(-50%, 100%);
  opacity: 0;
}
</style>