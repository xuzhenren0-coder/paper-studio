ALTER TABLE `members` ADD `send_time` text DEFAULT '08:00' NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `frequency` text DEFAULT 'daily' NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `weekdays` text DEFAULT '[0,1,2,3,4,5,6]' NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `difficulty` text DEFAULT 'beginner' NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `length` text DEFAULT 'standard' NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `preferences_version` integer DEFAULT 1 NOT NULL;--> statement-breakpoint
ALTER TABLE `members` ADD `schedule_effective_at` integer DEFAULT 0 NOT NULL;