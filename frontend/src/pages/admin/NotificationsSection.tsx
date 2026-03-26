import React from 'react'
import AddRoundedIcon from '@mui/icons-material/AddRounded'
import DeleteOutlineRoundedIcon from '@mui/icons-material/DeleteOutlineRounded'
import EditRoundedIcon from '@mui/icons-material/EditRounded'
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined'
import PlayArrowRoundedIcon from '@mui/icons-material/PlayArrowRounded'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import VisibilityRoundedIcon from '@mui/icons-material/VisibilityRounded'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import {
  createNotification,
  deleteNotification,
  listNotifications,
  previewNotification,
  replaceNotificationRecipients,
  runNotificationNow,
  type NotificationChannel,
  type NotificationConfig,
  type NotificationRecipient,
  type RecipientType,
  updateNotification,
} from '../../shared/api'

type Notice = { type: 'success' | 'error'; text: string } | null

type NotificationForm = {
  name: string
  channel: NotificationChannel
  enabled: boolean
  schedule_mode: 'inherit' | 'custom'
  interval_value: number
  interval_unit: 'minutes' | 'hours' | 'days' | 'weeks'
  time_of_day: string
  day_of_week: 'monday' | 'tuesday' | 'wednesday' | 'thursday' | 'friday' | 'saturday' | 'sunday'
  timezone: string
}

function formatDateTimePt(value?: string | null): string {
  if (!value) return 'n/a'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'n/a'
  const dd = String(date.getDate()).padStart(2, '0')
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const yyyy = date.getFullYear()
  const hh = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${dd}/${mm}/${yyyy} ${hh}:${min}`
}

function scheduleSummary(row: NotificationConfig): string {
  if (row.schedule_mode === 'inherit') return 'Automatic Sync Schedule'
  const unit = row.interval_unit
  const every = `Every ${row.interval_value} ${unit}`
  if (unit === 'minutes' || unit === 'hours') return every
  if (unit === 'days') return `${every} at ${row.time_of_day} (${row.timezone})`
  return `${every} on ${row.day_of_week} at ${row.time_of_day} (${row.timezone})`
}

function defaultForm(): NotificationForm {
  return {
    name: '',
    channel: 'email',
    enabled: true,
    schedule_mode: 'inherit',
    interval_value: 1,
    interval_unit: 'days',
    time_of_day: '00:00',
    day_of_week: 'monday',
    timezone: 'UTC',
  }
}

function defaultRecipientType(channel: NotificationChannel): RecipientType {
  return channel === 'telegram' ? 'telegram_chat' : 'email'
}

export default function NotificationsSection() {
  const [rows, setRows] = React.useState<NotificationConfig[]>([])
  const [loading, setLoading] = React.useState(false)
  const [creating, setCreating] = React.useState(false)
  const [runningId, setRunningId] = React.useState<number | null>(null)
  const [notice, setNotice] = React.useState<Notice>(null)
  const [createForm, setCreateForm] = React.useState<NotificationForm>(defaultForm)
  const [createRecipientType, setCreateRecipientType] = React.useState<RecipientType>('email')
  const [createRecipientValue, setCreateRecipientValue] = React.useState('')
  const [editingId, setEditingId] = React.useState<number | null>(null)
  const [editForm, setEditForm] = React.useState<NotificationForm>(defaultForm)
  const [recipientDrafts, setRecipientDrafts] = React.useState<Record<number, { type: RecipientType; value: string }>>({})
  const [previewById, setPreviewById] = React.useState<Record<number, string>>({})

  React.useEffect(() => {
    fetchRows()
  }, [])

  async function fetchRows() {
    setLoading(true)
    try {
      const data = await listNotifications()
      setRows(data)
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load notifications: ${error?.message || 'unknown error'}` })
    } finally {
      setLoading(false)
    }
  }

  function toPayload(form: NotificationForm) {
    return {
      name: form.name,
      channel: form.channel,
      enabled: form.enabled,
      schedule_mode: form.schedule_mode,
      interval_value: Number(form.interval_value || 1),
      interval_unit: form.interval_unit,
      time_of_day: form.time_of_day,
      day_of_week: form.day_of_week,
      timezone: form.timezone || 'UTC',
    }
  }

  async function onCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    if (!createForm.name.trim()) {
      setNotice({ type: 'error', text: 'Notification name is required.' })
      return
    }
    if (createForm.interval_value < 1) {
      setNotice({ type: 'error', text: 'Interval value must be at least 1.' })
      return
    }

    setCreating(true)
    try {
      const created = await createNotification(toPayload(createForm))
      const recipientValue = createRecipientValue.trim()
      if (recipientValue) {
        await replaceNotificationRecipients(created.id, [
          {
            type: createRecipientType,
            value: recipientValue,
            enabled: true,
          },
        ])
      }
      setCreateForm(defaultForm())
      setCreateRecipientType('email')
      setCreateRecipientValue('')
      await fetchRows()
      setNotice({ type: 'success', text: 'Notification created successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to create notification: ${error?.message || 'unknown error'}` })
    } finally {
      setCreating(false)
    }
  }

  function startEdit(row: NotificationConfig) {
    setEditingId(row.id)
    setEditForm({
      name: row.name,
      channel: row.channel,
      enabled: row.enabled,
      schedule_mode: row.schedule_mode,
      interval_value: row.interval_value,
      interval_unit: row.interval_unit,
      time_of_day: row.time_of_day,
      day_of_week: row.day_of_week,
      timezone: row.timezone,
    })
  }

  async function saveEdit(notificationId: number) {
    setNotice(null)
    if (!editForm.name.trim()) {
      setNotice({ type: 'error', text: 'Notification name is required.' })
      return
    }
    if (editForm.interval_value < 1) {
      setNotice({ type: 'error', text: 'Interval value must be at least 1.' })
      return
    }

    try {
      await updateNotification(notificationId, toPayload(editForm))
      setEditingId(null)
      await fetchRows()
      setNotice({ type: 'success', text: 'Notification updated successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update notification: ${error?.message || 'unknown error'}` })
    }
  }

  async function removeNotification(notificationId: number) {
    setNotice(null)
    if (!window.confirm('Delete this notification?')) return
    try {
      await deleteNotification(notificationId)
      if (editingId === notificationId) setEditingId(null)
      await fetchRows()
      setNotice({ type: 'success', text: 'Notification deleted successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to delete notification: ${error?.message || 'unknown error'}` })
    }
  }

  async function runNow(notificationId: number) {
    setNotice(null)
    setRunningId(notificationId)
    try {
      const out = await runNotificationNow(notificationId)
      await fetchRows()
      if (String(out?.status || '') === 'failed' || String(out?.status || '') === 'partial') {
        const errorMsg = String(out?.error || '').trim()
        setNotice({
          type: 'error',
          text: errorMsg
            ? `Run finished with status: ${out?.status}. Error: ${errorMsg}`
            : `Run finished with status: ${out?.status || 'unknown'}.`,
        })
      } else {
        setNotice({ type: 'success', text: `Run finished with status: ${out?.status || 'unknown'}` })
      }
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to run notification: ${error?.message || 'unknown error'}` })
    } finally {
      setRunningId(null)
    }
  }

  async function loadPreview(notificationId: number) {
    setNotice(null)
    try {
      const out = await previewNotification(notificationId)
      setPreviewById((prev) => ({
        ...prev,
        [notificationId]: String(out?.body || ''),
      }))
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load preview: ${error?.message || 'unknown error'}` })
    }
  }

  async function updateRecipients(notificationId: number, recipients: NotificationRecipient[]) {
    try {
      await replaceNotificationRecipients(notificationId, recipients)
      await fetchRows()
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update recipients: ${error?.message || 'unknown error'}` })
    }
  }

  async function addRecipient(notificationId: number) {
    const row = rows.find((x) => x.id === notificationId)
    if (!row) return
    const draft = recipientDrafts[notificationId] || { type: defaultRecipientType(row.channel), value: '' }
    const value = String(draft.value || '').trim()
    if (!value) {
      setNotice({ type: 'error', text: 'Recipient value is required.' })
      return
    }
    const recipients = [...(row.recipients || []), { type: draft.type, value, enabled: true }]
    await updateRecipients(notificationId, recipients)
    setRecipientDrafts((prev) => ({
      ...prev,
      [notificationId]: { type: defaultRecipientType(row.channel), value: '' },
    }))
    setNotice({ type: 'success', text: 'Recipient added.' })
  }

  async function removeRecipient(notificationId: number, idx: number) {
    const row = rows.find((x) => x.id === notificationId)
    if (!row) return
    const recipients = (row.recipients || []).filter((_, i) => i !== idx)
    await updateRecipients(notificationId, recipients)
    setNotice({ type: 'success', text: 'Recipient removed.' })
  }

  async function toggleRecipient(notificationId: number, idx: number) {
    const row = rows.find((x) => x.id === notificationId)
    if (!row) return
    const recipients = (row.recipients || []).map((r, i) => {
      if (i !== idx) return r
      return { ...r, enabled: !r.enabled }
    })
    await updateRecipients(notificationId, recipients)
    setNotice({ type: 'success', text: 'Recipient updated.' })
  }

  function renderScheduleFields(
    form: NotificationForm,
    setForm: React.Dispatch<React.SetStateAction<NotificationForm>>,
    prefix = ''
  ) {
    const isCustom = form.schedule_mode === 'custom'
    const showTime = isCustom && (form.interval_unit === 'days' || form.interval_unit === 'weeks')

    return (
      <>
        <Grid item xs={12} md={2}>
          <TextField
            label={(
              <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5 }}>
                {`${prefix}Schedule Mode`}
                <Tooltip
                  arrow
                  placement="top"
                  title="Automatic Sync Schedule uses the global sync schedule. The custom interval/time fields in this notification are ignored. If Automatic Sync Schedule is disabled, this notification will not run automatically."
                >
                  <Box component="span" sx={{ display: 'inline-flex', cursor: 'help' }} aria-label="Schedule mode help">
                    <InfoOutlinedIcon sx={{ fontSize: 14 }} />
                  </Box>
                </Tooltip>
              </Box>
            )}
            value={form.schedule_mode}
            onChange={(e) =>
              setForm((prev) => ({
                ...prev,
                schedule_mode: String(e.target.value || 'inherit') as any,
              }))
            }
            select
            size="small"
            fullWidth
          >
            <MenuItem value="inherit">Automatic Sync Schedule</MenuItem>
            <MenuItem value="custom">Custom</MenuItem>
          </TextField>
        </Grid>
        {isCustom ? (
          <>
            <Grid item xs={12} md={2}>
              <TextField
                label="Every"
                type="number"
                size="small"
                fullWidth
                inputProps={{ min: 1 }}
                value={form.interval_value}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    interval_value: Number(e.target.value || 1),
                  }))
                }
              />
            </Grid>
            <Grid item xs={12} md={2}>
              <TextField
                label="Unit"
                value={form.interval_unit}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    interval_unit: String(e.target.value || 'days') as any,
                  }))
                }
                select
                size="small"
                fullWidth
              >
                <MenuItem value="minutes">Minutes</MenuItem>
                <MenuItem value="hours">Hours</MenuItem>
                <MenuItem value="days">Days</MenuItem>
                <MenuItem value="weeks">Weeks</MenuItem>
              </TextField>
            </Grid>
            {showTime ? (
              <Grid item xs={12} md={2}>
                <TextField
                  label="Time (UTC)"
                  type="time"
                  size="small"
                  fullWidth
                  value={form.time_of_day}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      time_of_day: String(e.target.value || '00:00'),
                    }))
                  }
                  inputProps={{ step: 60 }}
                />
              </Grid>
            ) : null}
            {isCustom && form.interval_unit === 'weeks' ? (
              <Grid item xs={12} md={2}>
                <TextField
                  label="Day"
                  value={form.day_of_week}
                  onChange={(e) =>
                    setForm((prev) => ({
                      ...prev,
                      day_of_week: String(e.target.value || 'monday') as any,
                    }))
                  }
                  select
                  size="small"
                  fullWidth
                >
                  <MenuItem value="monday">Monday</MenuItem>
                  <MenuItem value="tuesday">Tuesday</MenuItem>
                  <MenuItem value="wednesday">Wednesday</MenuItem>
                  <MenuItem value="thursday">Thursday</MenuItem>
                  <MenuItem value="friday">Friday</MenuItem>
                  <MenuItem value="saturday">Saturday</MenuItem>
                  <MenuItem value="sunday">Sunday</MenuItem>
                </TextField>
              </Grid>
            ) : null}
          </>
        ) : null}
      </>
    )
  }

  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 2 }}>Portfolio Notifications</Typography>
        {notice ? <Alert severity={notice.type} sx={{ mb: 2 }}>{notice.text}</Alert> : null}

        <Box component="form" onSubmit={onCreate}>
          <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
            Create Notification
          </Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12} md={2}>
              <TextField
                label="Name"
                size="small"
                fullWidth
                value={createForm.name}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
              />
            </Grid>
            <Grid item xs={12} md={2}>
              <TextField
                label="Channel"
                size="small"
                fullWidth
                select
                value={createForm.channel}
                onChange={(e) => {
                  const channel = String(e.target.value || 'email') as NotificationChannel
                  setCreateForm((prev) => ({ ...prev, channel }))
                  setCreateRecipientType(defaultRecipientType(channel))
                }}
              >
                <MenuItem value="email">Email</MenuItem>
                <MenuItem value="telegram">Telegram</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={2}>
              <TextField
                label="Status"
                size="small"
                fullWidth
                select
                value={createForm.enabled ? 'enabled' : 'disabled'}
                onChange={(e) =>
                  setCreateForm((prev) => ({ ...prev, enabled: String(e.target.value) === 'enabled' }))
                }
              >
                <MenuItem value="enabled">Enabled</MenuItem>
                <MenuItem value="disabled">Disabled</MenuItem>
              </TextField>
            </Grid>

            {renderScheduleFields(createForm, setCreateForm)}

            <Grid item xs={12} md={2}>
              <TextField
                label="1st Recipient Type"
                value={createRecipientType}
                onChange={(e) => setCreateRecipientType(String(e.target.value || 'email') as RecipientType)}
                select
                size="small"
                fullWidth
              >
                <MenuItem value="email">Email</MenuItem>
                <MenuItem value="telegram_chat">Telegram Chat ID</MenuItem>
              </TextField>
            </Grid>
            <Grid item xs={12} md={2}>
              <TextField
                label="1st Recipient Value"
                size="small"
                fullWidth
                value={createRecipientValue}
                onChange={(e) => setCreateRecipientValue(e.target.value)}
                placeholder={createRecipientType === 'email' ? 'john@domain.com' : '123456789'}
              />
            </Grid>
            <Grid item xs={12} md={2} sx={{ display: 'flex', justifyContent: { xs: 'stretch', md: 'flex-end' } }}>
              <Button
                type="submit"
                variant="contained"
                fullWidth
                disabled={creating}
                startIcon={<AddRoundedIcon />}
              >
                {creating ? 'Creating...' : 'Create'}
              </Button>
            </Grid>
          </Grid>
        </Box>

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1 }}>
          Existing Notifications
        </Typography>

        <List dense>
          {!loading && rows.length === 0 ? (
            <ListItem>
              <ListItemText primary="No notifications configured." />
            </ListItem>
          ) : null}
          {rows.map((row) => {
            const isEditing = editingId === row.id
            const draft = recipientDrafts[row.id] || {
              type: defaultRecipientType(row.channel),
              value: '',
            }

            return (
              <ListItem key={row.id} divider sx={{ alignItems: 'flex-start' }}>
                <Stack spacing={1.5} sx={{ width: '100%' }}>
                  {!isEditing ? (
                    <>
                      <Stack
                        direction={{ xs: 'column', md: 'row' }}
                        spacing={1}
                        justifyContent="space-between"
                        alignItems={{ xs: 'flex-start', md: 'center' }}
                      >
                        <ListItemText
                          primary={`${row.name} (${row.channel})`}
                          secondary={
                            <>
                              <span>{scheduleSummary(row)}</span>
                              <br />
                              <span>Next run: {formatDateTimePt(row.next_run_at)}</span>
                              <br />
                              <span>Last sent: {formatDateTimePt(row.last_sent_at)}</span>
                            </>
                          }
                        />
                        <Stack direction="row" spacing={1}>
                          <Button size="small" variant="outlined" startIcon={<EditRoundedIcon />} onClick={() => startEdit(row)}>Edit</Button>
                          <Button size="small" variant="outlined" startIcon={<VisibilityRoundedIcon />} onClick={() => loadPreview(row.id)}>Preview</Button>
                          <Button
                            size="small"
                            variant="outlined"
                            startIcon={<PlayArrowRoundedIcon />}
                            disabled={runningId === row.id}
                            onClick={() => runNow(row.id)}
                          >
                            {runningId === row.id ? 'Running...' : 'Run now'}
                          </Button>
                          <Button size="small" color="error" variant="outlined" startIcon={<DeleteOutlineRoundedIcon />} onClick={() => removeNotification(row.id)}>Delete</Button>
                        </Stack>
                      </Stack>

                      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                        <Chip size="small" label={row.enabled ? 'Enabled' : 'Disabled'} color={row.enabled ? 'success' : 'default'} />
                        <Chip
                          size="small"
                          label={`Schedule: ${row.schedule_mode === 'inherit' ? 'Automatic Sync Schedule' : 'Custom'}`}
                        />
                        <Chip size="small" label={`Due: ${row.is_due ? 'yes' : 'no'}`} />
                      </Stack>
                    </>
                  ) : (
                    <Grid container spacing={1.5} alignItems="flex-start">
                      <Grid item xs={12} md={2}>
                        <TextField
                          label="Name"
                          size="small"
                          fullWidth
                          value={editForm.name}
                          onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
                        />
                      </Grid>
                      <Grid item xs={12} md={2}>
                        <TextField
                          label="Channel"
                          size="small"
                          fullWidth
                          select
                          value={editForm.channel}
                          onChange={(e) => setEditForm((prev) => ({ ...prev, channel: String(e.target.value || 'email') as NotificationChannel }))}
                        >
                          <MenuItem value="email">Email</MenuItem>
                          <MenuItem value="telegram">Telegram</MenuItem>
                        </TextField>
                      </Grid>
                      <Grid item xs={12} md={2}>
                        <TextField
                          label="Status"
                          size="small"
                          fullWidth
                          select
                          value={editForm.enabled ? 'enabled' : 'disabled'}
                          onChange={(e) => setEditForm((prev) => ({ ...prev, enabled: String(e.target.value) === 'enabled' }))}
                        >
                          <MenuItem value="enabled">Enabled</MenuItem>
                          <MenuItem value="disabled">Disabled</MenuItem>
                        </TextField>
                      </Grid>

                      {renderScheduleFields(editForm, setEditForm, '')}

                      <Grid item xs={12} md={2} sx={{ ml: { md: 'auto' } }}>
                        <Stack direction="row" spacing={1} justifyContent="flex-end">
                          <Button size="small" variant="contained" startIcon={<SaveRoundedIcon />} onClick={() => saveEdit(row.id)}>Save</Button>
                          <Button size="small" variant="outlined" onClick={() => setEditingId(null)}>Cancel</Button>
                        </Stack>
                      </Grid>
                    </Grid>
                  )}

                  <Box>
                    <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.75 }}>
                      Recipients
                    </Typography>
                    <Stack spacing={1}>
                      {(row.recipients || []).length === 0 ? (
                        <Typography variant="body2" color="text.secondary">No recipients yet.</Typography>
                      ) : null}
                      {(row.recipients || []).map((r, idx) => (
                        <Stack key={`${row.id}-${idx}-${r.value}`} direction={{ xs: 'column', md: 'row' }} spacing={1} justifyContent="space-between" alignItems={{ xs: 'flex-start', md: 'center' }}>
                          <Typography variant="body2">
                            {r.type}: {r.value}
                          </Typography>
                          <Stack direction="row" spacing={1}>
                            <Button size="small" variant="outlined" onClick={() => toggleRecipient(row.id, idx)}>
                              {r.enabled ? 'Disable' : 'Enable'}
                            </Button>
                            <Button size="small" color="error" variant="outlined" onClick={() => removeRecipient(row.id, idx)}>
                              Remove
                            </Button>
                          </Stack>
                        </Stack>
                      ))}

                      <Grid container spacing={1.5} sx={{ pt: 0.25 }}>
                        <Grid item xs={12} md={2}>
                          <TextField
                            label="Type"
                            size="small"
                            fullWidth
                            select
                            value={draft.type}
                            onChange={(e) =>
                              setRecipientDrafts((prev) => ({
                                ...prev,
                                [row.id]: {
                                  type: String(e.target.value || defaultRecipientType(row.channel)) as RecipientType,
                                  value: draft.value,
                                },
                              }))
                            }
                          >
                            <MenuItem value="email">Email</MenuItem>
                            <MenuItem value="telegram_chat">Telegram Chat ID</MenuItem>
                          </TextField>
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField
                            label="Recipient"
                            size="small"
                            fullWidth
                            value={draft.value}
                            onChange={(e) =>
                              setRecipientDrafts((prev) => ({
                                ...prev,
                                [row.id]: {
                                  type: draft.type,
                                  value: e.target.value,
                                },
                              }))
                            }
                            placeholder={draft.type === 'email' ? 'john@domain.com' : '123456789'}
                          />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <Button size="small" variant="contained" startIcon={<AddRoundedIcon />} onClick={() => addRecipient(row.id)}>
                            Add Recipient
                          </Button>
                        </Grid>
                      </Grid>
                    </Stack>
                  </Box>

                  {previewById[row.id] ? (
                    <Box sx={{ mt: 1 }}>
                      <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 0.5 }}>Preview</Typography>
                      <Box component="pre" sx={{
                        m: 0,
                        p: 1.5,
                        borderRadius: 1,
                        border: (theme) => `1px solid ${theme.palette.divider}`,
                        bgcolor: (theme) => theme.palette.action.hover,
                        whiteSpace: 'pre-wrap',
                        fontFamily: 'monospace',
                        fontSize: 12,
                      }}>
                        {previewById[row.id]}
                      </Box>
                    </Box>
                  ) : null}
                </Stack>
              </ListItem>
            )
          })}
        </List>
      </CardContent>
    </Card>
  )
}
