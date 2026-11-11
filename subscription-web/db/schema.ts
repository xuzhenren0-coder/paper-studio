import {sqliteTable,text,integer} from 'drizzle-orm/sqlite-core';
export const members=sqliteTable('members',{
 id:text('id').primaryKey(),email:text('email').notNull().unique(),name:text('name').notNull(),topics:text('topics').notNull(),status:text('status').notNull(),
 generation:text('generation').notNull(),unsubscribeHash:text('unsubscribe_hash').notNull().unique(),unsubscribeCipher:text('unsubscribe_cipher').notNull(),
 verifiedAt:integer('verified_at'),adminPaused:integer('admin_paused').notNull().default(0),createdAt:integer('created_at').notNull(),updatedAt:integer('updated_at').notNull(),
 sendTime:text('send_time').notNull().default('08:00'),frequency:text('frequency').notNull().default('daily'),weekdays:text('weekdays').notNull().default('[0,1,2,3,4,5,6]'),difficulty:text('difficulty').notNull().default('beginner'),length:text('length').notNull().default('standard'),preferencesVersion:integer('preferences_version').notNull().default(1),scheduleEffectiveAt:integer('schedule_effective_at').notNull().default(0)
});
export const tokens=sqliteTable('member_tokens',{tokenHash:text('token_hash').primaryKey(),memberId:text('member_id').notNull(),generation:text('generation').notNull(),purpose:text('purpose').notNull(),expiresAt:integer('expires_at').notNull(),usedAt:integer('used_at')});
export const sessions=sqliteTable('member_sessions',{tokenHash:text('token_hash').primaryKey(),memberId:text('member_id').notNull(),expiresAt:integer('expires_at').notNull()});
export const outbox=sqliteTable('member_outbox',{id:text('id').primaryKey(),memberId:text('member_id').notNull(),payload:text('payload').notNull(),status:text('status').notNull(),createdAt:integer('created_at').notNull(),expiresAt:integer('expires_at').notNull(),finishedAt:integer('finished_at')});
export const nonces=sqliteTable('bridge_nonces',{nonce:text('nonce').primaryKey(),expiresAt:integer('expires_at').notNull()});
