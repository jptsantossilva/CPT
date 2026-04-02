import React from 'react'
import SaveRoundedIcon from '@mui/icons-material/SaveRounded'
import { Alert, Box, Button, Card, CardContent, Grid, MenuItem, Stack, TextField, Typography } from '@mui/material'
import NotificationsSection from './admin/NotificationsSection'
import { fetchSyncSchedule, updateSyncSchedule } from '../shared/api'

type Notice = { type: 'success' | 'error'; text: string } | null

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

export default function Automation() {
  const [scheduleLoading, setScheduleLoading] = React.useState(false)
  const [schedule, setSchedule] = React.useState<any | null>(null)
  const [scheduleForm, setScheduleForm] = React.useState({
    enabled: false,
    interval_value: 1,
    interval_unit: 'days',
    time_of_day: '00:00',
    day_of_week: 'monday',
  })
  const [notice, setNotice] = React.useState<Notice>(null)
  const isDayBasedSchedule = scheduleForm.interval_unit === 'days' || scheduleForm.interval_unit === 'weeks'

  React.useEffect(() => {
    fetchSchedule()
  }, [])

  async function fetchSchedule() {
    try {
      const scheduleConfig = await fetchSyncSchedule()
      setSchedule(scheduleConfig)
      setScheduleForm({
        enabled: Boolean(scheduleConfig?.enabled),
        interval_value: Number(scheduleConfig?.interval_value || 1),
        interval_unit: String(scheduleConfig?.interval_unit || 'days'),
        time_of_day: String(scheduleConfig?.time_of_day || '00:00'),
        day_of_week: String(scheduleConfig?.day_of_week || 'monday'),
      })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to load sync schedule: ${error?.message || 'unknown error'}` })
    }
  }

  async function saveSchedule(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setNotice(null)
    if (scheduleForm.interval_value < 1) {
      setNotice({ type: 'error', text: 'Interval value must be at least 1.' })
      return
    }
    setScheduleLoading(true)
    try {
      const updated = await updateSyncSchedule({
        enabled: scheduleForm.enabled,
        interval_value: Number(scheduleForm.interval_value),
        interval_unit: scheduleForm.interval_unit as any,
        time_of_day: String(scheduleForm.time_of_day || '00:00'),
        day_of_week: String(scheduleForm.day_of_week || 'monday'),
      })
      setSchedule(updated)
      setScheduleForm({
        enabled: Boolean(updated?.enabled),
        interval_value: Number(updated?.interval_value || 1),
        interval_unit: String(updated?.interval_unit || 'days'),
        time_of_day: String(updated?.time_of_day || '00:00'),
        day_of_week: String(updated?.day_of_week || 'monday'),
      })
      setNotice({ type: 'success', text: 'Sync schedule updated successfully.' })
    } catch (error: any) {
      setNotice({ type: 'error', text: `Failed to update sync schedule: ${error?.message || 'unknown error'}` })
    } finally {
      setScheduleLoading(false)
    }
  }

  return (
    <Stack spacing={2}>
      {notice ? <Alert severity={notice.type}>{notice.text}</Alert> : null}

      <Card variant="outlined">
        <CardContent>
          <Typography variant="h6" sx={{ mb: 2 }}>Automatic Sync Schedule</Typography>
          <Box component="form" onSubmit={saveSchedule}>
            <Grid container spacing={1.5} alignItems="flex-start">
              <Grid item xs={12} md={2}>
                <TextField
                  label="Mode"
                  value={scheduleForm.enabled ? 'enabled' : 'disabled'}
                  onChange={(e) =>
                    setScheduleForm((prev) => ({
                      ...prev,
                      enabled: String(e.target.value) === 'enabled',
                    }))
                  }
                  select
                  size="small"
                  fullWidth
                >
                  <MenuItem value="disabled">Disabled</MenuItem>
                  <MenuItem value="enabled">Enabled</MenuItem>
                </TextField>
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  label="Every"
                  type="number"
                  size="small"
                  fullWidth
                  inputProps={{ min: 1 }}
                  value={scheduleForm.interval_value}
                  onChange={(e) =>
                    setScheduleForm((prev) => ({
                      ...prev,
                      interval_value: Number(e.target.value || 1),
                    }))
                  }
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  label="Unit"
                  value={scheduleForm.interval_unit}
                  onChange={(e) =>
                    setScheduleForm((prev) => ({
                      ...prev,
                      interval_unit: String(e.target.value || 'days'),
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
              {isDayBasedSchedule ? (
                <Grid item xs={12} md={2}>
                  <TextField
                    label="Time (UTC)"
                    type="time"
                    size="small"
                    fullWidth
                    value={scheduleForm.time_of_day}
                    onChange={(e) =>
                      setScheduleForm((prev) => ({
                        ...prev,
                        time_of_day: String(e.target.value || '00:00'),
                      }))
                    }
                    inputProps={{ step: 60 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    Time is in UTC
                  </Typography>
                </Grid>
              ) : null}
              {scheduleForm.interval_unit === 'weeks' ? (
                <Grid item xs={12} md={2}>
                  <TextField
                    label="Day of Week"
                    value={scheduleForm.day_of_week}
                    onChange={(e) =>
                      setScheduleForm((prev) => ({
                        ...prev,
                        day_of_week: String(e.target.value || 'monday'),
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
                  <Typography variant="caption" color="text.secondary">
                    Used for weekly sync
                  </Typography>
                </Grid>
              ) : null}
              <Grid
                item
                xs={12}
                md={2}
                sx={{
                  display: 'flex',
                  justifyContent: { xs: 'stretch', md: 'flex-end' },
                  ml: { xs: 0, md: 'auto' },
                }}
              >
                <Button
                  type="submit"
                  variant="contained"
                  fullWidth
                  disabled={scheduleLoading}
                  startIcon={<SaveRoundedIcon />}
                >
                  {scheduleLoading ? 'Saving...' : 'Save Schedule'}
                </Button>
              </Grid>
              <Grid item xs={12}>
                <Typography variant="body2" color="text.secondary">
                  Next run: {formatDateTimePt(schedule?.next_run_at)}
                </Typography>
              </Grid>
            </Grid>
          </Box>
        </CardContent>
      </Card>

      <NotificationsSection />
    </Stack>
  )
}
