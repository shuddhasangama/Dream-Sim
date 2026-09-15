// Local browser development only; imported into a separate module for testing.
export function previewTransport() {
  let active = false;
  const ok = (data, status=200) => ({status, data:{data,error:null}});
  return async (path, method, body) => {
    if (path.endsWith('/auth/request')) return ok({challenge_id:'local-preview'},202);
    if (path.endsWith('/auth/verify')) {
      if (body.code !== '123456') return {status:401,data:{error:{message:'Preview code is 123456.'},data:null}};
      active=true;
      return ok({access_token:'preview-access',refresh_token:'preview-refresh',expires_in:900});
    }
    if (path.endsWith('/auth/logout')) { active=false; return ok({logged_out:true}); }
    if (!active) return {status:401,data:{error:{message:'Sign in again.'},data:null}};
    if (path.endsWith('/dashboard')) return ok({user:{display_name:'Preview profile',journey_state:'dating',bgv_status:'verified'},current_lock_in:null,current_date_plan:null,next_action:{headline:'Your next chapter starts here',body:'Take a moment to review your profile before meeting someone new.'},clock:{mode:'simulation',week:1}});
    if (path.endsWith('/profile')) return ok({stats:{age:30,city:'Bangalore',profession:'Engineering',diet:'Vegetarian'},visions:[{key:'Intimacy',stance:['Emotional']},{key:'Cohabitate',stance:['Chores split']} ]});
    throw new Error('Unsupported preview request');
  };
}
