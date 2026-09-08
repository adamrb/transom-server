/**
 * The design system. Import from '@/components' (or a single folder for tree-shaking clarity).
 * One folder per component: index.tsx (the component + its props type) and <Name>.test.tsx.
 * Every component is styled with Tailwind utilities that map onto the M3 tokens in src/theme.
 */
export { Avatar } from './Avatar';
export type { AvatarProps, AvatarKind } from './Avatar';
export { Banner } from './Banner';
export type { BannerProps, BannerTone } from './Banner';
export { BottomNav } from './BottomNav';
export type { BottomNavProps } from './BottomNav';
export { Button } from './Button';
export type { ButtonProps, ButtonVariant, ButtonSize } from './Button';
export { Card } from './Card';
export type { CardProps, CardTone } from './Card';
export { Chip, StatusChip } from './Chip';
export type { ChipProps, StatusChipProps, StatusTone } from './Chip';
export { Dialog, ConfirmDialog } from './Dialog';
export type { DialogProps, ConfirmDialogProps } from './Dialog';
export { EmptyState } from './EmptyState';
export type { EmptyStateProps } from './EmptyState';
export { Icon, ICON_NAMES } from './Icon';
export type { IconProps, IconName, IconSize } from './Icon';
export { IconButton } from './IconButton';
export type { IconButtonProps, IconButtonVariant, IconButtonSize } from './IconButton';
export { LinearProgress } from './LinearProgress';
export type { LinearProgressProps } from './LinearProgress';
export { ListItem } from './ListItem';
export type { ListItemProps } from './ListItem';
export { Markdown } from './Markdown';
export type { MarkdownProps } from './Markdown';
export { NavRail, NavRailItem } from './NavRail';
export type { NavRailProps, NavDestination } from './NavRail';
export { Popover, MenuItem, MenuSeparator, MenuLabel } from './Popover';
export type { PopoverProps, MenuItemProps } from './Popover';
export { ProgressRing } from './ProgressRing';
export type { ProgressRingProps } from './ProgressRing';
export { SearchBar } from './SearchBar';
export type { SearchBarProps } from './SearchBar';
export { SegmentedButton } from './SegmentedButton';
export type { SegmentedButtonProps, SegmentOption } from './SegmentedButton';
export { Skeleton, SkeletonListItem, SkeletonText } from './Skeleton';
export type { SkeletonProps } from './Skeleton';
export { Slider } from './Slider';
export type { SliderProps } from './Slider';
export { SnackbarProvider, SnackbarHost, useSnackbar } from './Snackbar';
export type { SnackbarApi, SnackbarOptions, SnackbarAction } from './Snackbar';
export { Switch } from './Switch';
export type { SwitchProps } from './Switch';
export { Tabs } from './Tabs';
export type { TabsProps, TabItem } from './Tabs';
export { TextField } from './TextField';
export type { TextFieldProps, TextAreaFieldProps, AnyTextFieldProps } from './TextField';
export { TopAppBar } from './TopAppBar';
export type { TopAppBarProps } from './TopAppBar';
