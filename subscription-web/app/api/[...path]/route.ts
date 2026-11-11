import {env} from 'cloudflare:workers';
// @ts-ignore Shared module is also exercised with Node's built-in SQLite.
import {handleMembers} from '../../../lib/members.mjs';
export const dynamic='force-dynamic';
export async function GET(request:Request){return handleMembers(request,{DB:env.DB,MEMBER_BRIDGE_SECRET:env.MEMBER_BRIDGE_SECRET||process.env.MEMBER_BRIDGE_SECRET,MEMBER_PUBLIC_ORIGIN:env.MEMBER_PUBLIC_ORIGIN||process.env.MEMBER_PUBLIC_ORIGIN});}
export const POST=GET;
